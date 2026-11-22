# Using Deque as a FIFO Queue or LIFO Stack

## 1. One structure, two rules for choosing the next item

An application receives tasks A, B, and C. If it needs to process the earliest task first, the retrieval order is A, B, C. However, when storing actions for undo, the most recent action usually must be retrieved first: C, B, A.

These two requirements use two policies:

- **FIFO — First In, First Out:** first in, first out; commonly called a queue.
- **LIFO — Last In, First Out:** last in, first out; commonly called a stack.

`Deque<E>` is an interface for a sequence that supports adding, inspecting, and removing elements at both ends. The name is short for “double-ended queue”. Because it has two ends for operations, Deque can express both FIFO and LIFO.

What determines the behavior is not just the class name, but also the **pair of insertion end and removal end**:

```text
FIFO: add at one end, remove from the opposite end
LIFO: add and remove at the same end
```

In Java, the common conventions are:

```text
FIFO: offerLast / pollFirst
LIFO: push / pop, equivalent to addFirst / removeFirst
```

This article uses `ArrayDeque` as the concrete implementation in single-threaded code. The goal is to choose the right operations, understand the empty case, and see how the FIFO/LIFO policy changes how an algorithm processes data.

## 2. Head and tail conventions must be clear

Let us draw a Deque in order from head to tail:

```text
head / first                          tail / last
     A  <------------>  B  <------------>  C
```

The names `First` and `Last` refer to the ends of the current sequence. “First” does not automatically mean the earliest added element: if you repeatedly add at the head, the newest element will be first.

There are three groups of operations at each end:

| Action | First end | Last end |
|---|---|---|
| Add | `addFirst`, `offerFirst` | `addLast`, `offerLast` |
| Retrieve and remove | `removeFirst`, `pollFirst` | `removeLast`, `pollLast` |
| Peek only | `getFirst`, `peekFirst` | `getLast`, `peekLast` |

Method names indicate both the action and the end being operated on. The pairs in the same cell differ mainly in how they represent a normal failure such as being empty or lacking space; a later section distinguishes them specifically.

According to [Deque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html), this interface extends Queue while providing operations at both ends. Deque is not a List with index-based access.

One way to declare it:

```java
// Snippet; requires importing java.util.Deque and java.util.ArrayDeque.
Deque<String> pending = new ArrayDeque<>();
```

`Deque` expresses the capability the calling code needs; `ArrayDeque` chooses the storage representation. Using an interface type does not automatically give the object synchronization or immutability.

## 3. Using Deque as a FIFO queue

### 3.1. Rule: add at the tail, remove from the head

Insert A, B, and C in order at the tail:

```text
offerLast(A): [A]
offerLast(B): [A, B]
offerLast(C): [A, B, C]
```

Then retrieve from the head:

```text
pollFirst(): A       remaining [B, C]
pollFirst(): B       remaining [C]
pollFirst(): C       remaining []
```

The invariant to maintain is: among the pending elements, the earliest added element is at the next removal end.

Usage pattern with ArrayDeque:

```java
// Snippet illustrating FIFO processing in a single thread.
Deque<String> jobs = new ArrayDeque<>();
jobs.offerLast("A");
jobs.offerLast("B");
jobs.offerLast("C");

String next;
while ((next = jobs.pollFirst()) != null) {
    process(next);
}
```

`process` is business logic in the surrounding program, not a built-in Java function. This snippet is not yet a standalone program.

The pattern of using null to terminate fits here because ArrayDeque does not accept null elements. `pollFirst` returning null means there are no elements left, without being confused with a real null task.

### 3.2. You can use only the Queue interface

If the code only needs FIFO and does not need to see both ends:

```java
// Snippet; requires importing java.util.Queue and ArrayDeque.
Queue<String> jobs = new ArrayDeque<>();
jobs.offer("A");
jobs.offer("B");
String next = jobs.poll();  // "A"
```

With a Deque such as ArrayDeque, the methods inherited from Queue correspond as follows:

| Via Queue | Via Deque |
|---|---|
| `add(e)` | `addLast(e)` |
| `offer(e)` | `offerLast(e)` |
| `remove()` | `removeFirst()` |
| `poll()` | `pollFirst()` |
| `element()` | `getFirst()` |
| `peek()` | `peekFirst()` |

Using the Queue type restricts that part of the code to operating only through the queue interface. It does not prevent another part of the code holding the same Deque object from calling operations on the other end; ownership and reference sharing still need to be clear.

Nor should you generalize that every Queue implementation is FIFO. [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html) also includes other policies, such as priority queues. The examples in this article are FIFO because the chosen ArrayDeque object and pair of operations follow that rule.

### 3.3. FIFO does not sort by value

If you add `"C"`, `"A"`, `"B"` in sequence, a FIFO queue retrieves C, A, B. It preserves the waiting order, not lexicographical order.

If you add two tasks that are equal according to equals, Deque can still keep both occurrences. This is not a deduplicating Set.

## 4. Using Deque as a LIFO stack

### 4.1. Choosing the first end as the top

Commonly used methods:

```java
// Snippet illustrating LIFO.
Deque<String> history = new ArrayDeque<>();
history.push("A");
history.push("B");
history.push("C");

String top = history.peek();   // "C", peek only
String removed = history.pop(); // "C", retrieve and remove
```

With Deque:

| Method | Meaning |
|---|---|
| `push(e)` | Add at the head, equivalent to `addFirst(e)` |
| `pop()` | Retrieve and remove the head, equivalent to `removeFirst()` |
| `peek()` | Peek at the head, equivalent to `peekFirst()`; null when empty |
| `getFirst()` | Peek at the head, but throws an exception when empty |

After three pushes:

```text
push(A): [A]
push(B): [B, A]
push(C): [C, B, A]
          ^
         top
```

Pop retrieves C, B, A in order. The invariant is that the most recently pushed element among those not yet removed is at the top.

### 4.2. Do not confuse variable names with method roles

A variable named `queue` that calls `push` and `pop` still has LIFO behavior. A variable named `stack` that adds at the tail and removes from the head still has FIFO behavior.

Variable names should express intent, but the pair of operations is what actually implements that intent.

If you want to remove from the top while handling emptiness with null, you can use `pollFirst()` instead of pop. LIFO still holds because you are still removing from the exact end used for adding.

### 4.3. Can the last end be used as the top?

Yes. `addLast` with `removeLast`, or `offerLast` with `pollLast`, also produces LIFO. Both adding and removing happen at the same end.

However, when using the names `push` and `pop`, the top by API convention is first. Do not push at first and then pop with removeLast if you want LIFO.

A quick self-check table:

| Insertion end | Removal end | Policy by insertion order |
|---|---|---|
| Last | First | FIFO |
| First | Last | FIFO if this pair is used consistently |
| First | First | LIFO |
| Last | Last | LIFO |

Both FIFO rows are mathematically valid for a sequence, but Java's Queue convention uses add last, remove first. Choosing one clear convention and staying consistent makes code easier to read.

## 5. Program 1: same input, two output orders

Save the file `DequeFifoLifoDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Queue;

public class DequeFifoLifoDemo {
    public static void main(String[] args) {
        List<String> input = List.of("A", "B", "C");

        Deque<String> fifo = new ArrayDeque<>();
        for (String item : input) {
            fifo.offerLast(item);
        }
        System.out.println("FIFO head to tail = " + fifo);
        System.out.println("FIFO next = " + fifo.peekFirst());
        System.out.println("FIFO size after peek = " + fifo.size());

        List<String> fifoOutput = new ArrayList<>();
        String item;
        while ((item = fifo.pollFirst()) != null) {
            fifoOutput.add(item);
        }
        System.out.println("FIFO output = " + fifoOutput);
        System.out.println("FIFO empty = " + fifo.isEmpty());

        Deque<String> lifo = new ArrayDeque<>();
        for (String value : input) {
            lifo.push(value);
        }
        System.out.println("LIFO head to tail = " + lifo);
        System.out.println("LIFO top = " + lifo.peek());

        List<String> lifoOutput = new ArrayList<>();
        while (!lifo.isEmpty()) {
            lifoOutput.add(lifo.pop());
        }
        System.out.println("LIFO output = " + lifoOutput);
        System.out.println("LIFO empty = " + lifo.isEmpty());

        Queue<String> queueApi = new ArrayDeque<>(input);
        List<String> queueOutput = new ArrayList<>();
        while ((item = queueApi.poll()) != null) {
            queueOutput.add(item);
        }
        System.out.println("Queue API output = " + queueOutput);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 DequeFifoLifoDemo.java
java DequeFifoLifoDemo
```

Output of the verification run:

```text
FIFO head to tail = [A, B, C]
FIFO next = A
FIFO size after peek = 3
FIFO output = [A, B, C]
FIFO empty = true
LIFO head to tail = [C, B, A]
LIFO top = C
LIFO output = [C, B, A]
LIFO empty = true
Queue API output = [A, B, C]
```

The programs in this article use language features and APIs available in Java 17 and later. They were compiled with `--release 17` and verified on Azul OpenJDK 24.0.2.

Key takeaways:

- FIFO keeps the input A, B, C in order from head to tail, then retrieves them in the same order.
- LIFO pushes at the head, so the sequence from head to tail is C, B, A.
- Peek does not reduce size.
- Poll or pop retrieves and removes the element.
- Using the Queue interface on ArrayDeque gives the same FIFO behavior as the corresponding last/first operations.

Do not read `[C, B, A]` of the stack as “ArrayDeque reverses the array when printing”. That is the logical sequence created by three insertions at the head.

Also, do not only check that all three elements were retrieved. Both FIFO and LIFO contain A, B, and C; the difference the problem must preserve is the retrieval order.

## 6. Choosing how to handle emptiness and capacity limits

Deque provides groups of methods to express how failures are handled.

### 6.1. Retrieving and peeking when empty

| Action | Throws `NoSuchElementException` if empty | Returns null if empty |
|---|---|---|
| Peek head | `getFirst()` | `peekFirst()` |
| Peek tail | `getLast()` | `peekLast()` |
| Retrieve and remove head | `removeFirst()` | `pollFirst()` |
| Retrieve and remove tail | `removeLast()` | `pollLast()` |

`pop()` belongs to the head-removal group that throws an exception. `peek()` on **Deque** belongs to the group that returns null.

Choose based on the meaning of the processing flow:

- A queue temporarily running out of work is normal: poll usually expresses this well.
- The algorithm already guarantees an element must exist: remove or pop can expose a faulty assumption.
- Only need to inspect the next task: peek or get, do not use a removing method.

Do not use exceptions as normal loop control to detect the end of data when a status-returning method fits.

### 6.2. Adding to a capacity-bounded structure

`addFirst`/`addLast` can throw IllegalStateException if a bounded implementation has no room left. `offerFirst`/`offerLast` can return false in such a full-capacity situation.

However, offer does not mean “every error is converted to false”. For example, passing null into ArrayDeque still throws NullPointerException.

ArrayDeque grows its capacity as needed; it is not a fixed-capacity queue set by the constructor parameter. If the problem requires bounding pending items or waiting until space is available, you must choose an appropriate implementation and API; standard Queue/Deque does not provide waiting mechanisms on its own.

### 6.3. Do not use null as task data in ArrayDeque

Null is rejected so that methods like poll and peek can use null as a sentinel for no element.

If you need a task meaning “missing data” or “end”, represent it with an explicit value or data type rather than stuffing null into a structure that does not accept it.

The Deque interface can be implemented by classes with different null policies, but using null in a queue or stack often creates ambiguity with null-returning methods. The patterns in this article rely on ArrayDeque's non-null contract.

## 7. Program 2: verifying empty and null APIs

Save the file `DequeEmptyPolicyDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.NoSuchElementException;

public class DequeEmptyPolicyDemo {
    static void showEmptyFailure(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NoSuchElementException");
        } catch (NoSuchElementException ex) {
            System.out.println(label + " = " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Deque<String> values = new ArrayDeque<>();

        System.out.println("empty peekFirst = " + values.peekFirst());
        System.out.println("empty peekLast = " + values.peekLast());
        System.out.println("empty pollFirst = " + values.pollFirst());
        System.out.println("empty pollLast = " + values.pollLast());
        System.out.println("size after empty reads = " + values.size());

        showEmptyFailure("empty getFirst", values::getFirst);
        showEmptyFailure("empty getLast", values::getLast);
        showEmptyFailure("empty removeFirst", values::removeFirst);
        showEmptyFailure("empty removeLast", values::removeLast);
        showEmptyFailure("empty pop", values::pop);

        try {
            values.offerLast(null);
        } catch (NullPointerException ex) {
            System.out.println("offer null = "
                    + ex.getClass().getSimpleName());
        }
        try {
            values.push(null);
        } catch (NullPointerException ex) {
            System.out.println("push null = "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("offer X = " + values.offerLast("X"));
        System.out.println("peek X = " + values.peekFirst());
        System.out.println("size after peek X = " + values.size());
        System.out.println("pop X = " + values.pop());
        System.out.println("size after pop X = " + values.size());

        Deque<String> growing = new ArrayDeque<>(1);
        growing.offerLast("A");
        growing.offerLast("B");
        growing.offerLast("C");
        System.out.println("initial capacity is not limit = " + growing);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 DequeEmptyPolicyDemo.java
java DequeEmptyPolicyDemo
```

Output of the verification run:

```text
empty peekFirst = null
empty peekLast = null
empty pollFirst = null
empty pollLast = null
size after empty reads = 0
empty getFirst = NoSuchElementException
empty getLast = NoSuchElementException
empty removeFirst = NoSuchElementException
empty removeLast = NoSuchElementException
empty pop = NoSuchElementException
offer null = NullPointerException
push null = NullPointerException
offer X = true
peek X = X
size after peek X = 1
pop X = X
size after pop X = 0
initial capacity is not limit = [A, B, C]
```

The `showEmptyFailure` helper simply centralizes exception checking in the example. If a method does not throw the expected exception, it throws AssertionError so it does not print a misleading result.

### 7.1. Null-returning methods do not mutate an empty collection

Calls to peek and poll on an empty Deque all return null, and size remains 0.

For a Deque containing X, peek returns X and size remains 1; pop returns X and size drops to 0. Therefore, “inspecting” and “removing” cannot be swapped just because they return the same value in one example.

### 7.2. Offer can still throw an exception

`offerLast(null)` throws NullPointerException. Do not write code that only checks the boolean return value and assume all invalid inputs are handled.

If code receives external data, define a null policy before inserting into the Deque. Ending a loop when poll returns null is only unambiguous when member data cannot be null.

### 7.3. Initial capacity is not a limit

`new ArrayDeque<>(1)` still holds A, B, and C in the program. The constructor prepares an initial capacity sufficient for the stated need; it does not enforce “at most one element”.

This matters if a Deque is used to hold pending tasks. If you need a real business limit, you must design or choose a structure with a bounded contract; do not use initial capacity as a count-limiting mechanism.

## 8. Why is ArrayDeque the common choice in single-threaded code?

[ArrayDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html) describes it as a resizable-array Deque that prohibits null elements and is not thread-safe for concurrent access without external coordination.

A helpful mental model is a circular array: the structure tracks the positions of both ends, so adding or removing at the head does not require shifting every element the way removing the first element of a naive linear array does.

When the array needs to grow, an operation may have to allocate and copy data. Therefore, cost is typically analyzed as **amortized** over a sequence of operations.

With ArrayDeque, common operations at both ends have amortized constant cost. However, do not generalize that every Deque method is O(1):

| Operation | Appropriate analysis for ArrayDeque |
|---|---|
| Add/remove at both ends | Amortized constant for common operations |
| Peek at both ends | Does not scan the entire sequence |
| `contains(x)` | May need to search through elements |
| `remove(x)` by value | May need to search and adjust the sequence |
| Iterate all n elements | Must process n elements |
| Store n elements | Needs memory for the structure and data references |

If the problem mainly adds and removes at the ends, Deque expresses the right operations. If you frequently need index-based access or sorting by a criterion, evaluate another structure instead of forcing Deque to do everything.

You do not need a homemade microbenchmark with a few clock calls to conclude that ArrayDeque is always faster than every other class. Choose first based on contract, operations, and environment; measure when actual performance needs evaluation.

### 8.1. Compared to the legacy Stack

The [Stack Java 17 documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Stack.html) recommends using Deque and its implementations instead of the legacy Stack class for LIFO operations.

A declaration that makes intent clear is:

```java
Deque<Integer> stack = new ArrayDeque<>();
```

When migrating legacy code, also check the emptiness policy. Deque.pop throws NoSuchElementException when empty, and Deque.peek returns null. Do not assume every exception detail or behavior of the legacy Stack is preserved just because the methods share the same names.

### 8.2. Multi-threaded support is a separate decision

An ArrayDeque used with proper FIFO can still be shared incorrectly across multiple threads. Which end you remove from does not provide atomicity for sequences of operations.

If multiple parties need to produce or consume work, choose an appropriate coordination mechanism or concurrent/blocking collection. Do not switch to another class just because its name contains Queue and assume all ordering, capacity, and waiting requirements are solved.

The examples in this article are single-threaded code; checking for empty and then popping is valid under that assumption. Do not carry that assumption unchanged into a context with concurrent updates.

## 9. FIFO and LIFO change how a tree is traversed

Consider the binary tree:

```text
          A
        /          B     C
      /           D   E     F
```

Suppose when discovering child nodes, we want to prioritize left before right.

### 9.1. FIFO queue: level by level

Start with A. After processing A, add B then C at the tail:

```text
remove A -> queue [B, C]
remove B -> queue [C, D, E]
remove C -> queue [D, E, F]
```

Nodes that have been waiting longer are retrieved first. The result is:

```text
A, B, C, D, E, F
```

This is breadth-first traversal.

### 9.2. LIFO stack: going deep down a branch

After processing A, to retrieve B next you must push C first, then push B:

```text
push C then B -> stack [B, C]
pop B
push E then D -> stack [D, E, C]
```

D is retrieved before E, and the entire B branch is processed before C. The result is:

```text
A, B, D, E, C, F
```

This is depth-first preorder traversal.

The core point is: **with LIFO, the order of pushing multiple elements must be reversed if you want the processing order to match the original priority list**.

A tree is just one example of choosing the next item. The same idea appears when traversing directories, processing nested structures, or managing pending computation steps.

## 10. Program 3: one tree, two processing policies

Save the file `DequeTreeTraversalDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

public class DequeTreeTraversalDemo {
    record Node(String name, Node left, Node right) {
    }

    static List<String> breadthFirst(Node root) {
        if (root == null) {
            return List.of();
        }

        Deque<Node> pending = new ArrayDeque<>();
        List<String> result = new ArrayList<>();
        pending.offerLast(root);

        while (!pending.isEmpty()) {
            Node current = pending.removeFirst();
            result.add(current.name());

            if (current.left() != null) {
                pending.offerLast(current.left());
            }
            if (current.right() != null) {
                pending.offerLast(current.right());
            }
        }
        return result;
    }

    static List<String> depthFirst(Node root) {
        if (root == null) {
            return List.of();
        }

        Deque<Node> pending = new ArrayDeque<>();
        List<String> result = new ArrayList<>();
        pending.push(root);

        while (!pending.isEmpty()) {
            Node current = pending.pop();
            result.add(current.name());

            if (current.right() != null) {
                pending.push(current.right());
            }
            if (current.left() != null) {
                pending.push(current.left());
            }
        }
        return result;
    }

    public static void main(String[] args) {
        Node root = new Node("A",
                new Node("B",
                        new Node("D", null, null),
                        new Node("E", null, null)),
                new Node("C",
                        null,
                        new Node("F", null, null)));

        System.out.println("breadth first FIFO = " + breadthFirst(root));
        System.out.println("depth first LIFO = " + depthFirst(root));
        System.out.println("empty tree FIFO = " + breadthFirst(null));
        System.out.println("empty tree LIFO = " + depthFirst(null));
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 DequeTreeTraversalDemo.java
java DequeTreeTraversalDemo
```

Output of the verification run:

```text
breadth first FIFO = [A, B, C, D, E, F]
depth first LIFO = [A, B, D, E, C, F]
empty tree FIFO = []
empty tree LIFO = []
```

### 10.1. Null child links are not put into the Deque

Leaf nodes have null child links. The code checks links before adding, so ArrayDeque only contains real Node instances.

A null root is handled immediately by returning an empty list. There is no need to push null into the queue as a special node.

This is the difference between a nullable data field and the element itself added to the Deque. Algorithm input data may have empty links, while the collection being used still upholds a non-null contract.

### 10.2. The queue preserves discovery order

In breadthFirst, the left child then the right child are added at the tail. Nodes already waiting remain toward the head, so a node on the next level does not jump ahead of nodes on the current level.

Each Node is processed once in the example tree. The returned result is separate from the Deque used as the pending buffer.

### 10.3. The stack reverses the insertion order of child nodes

In depthFirst, the code pushes the right child first, then the left child. The left child therefore sits at the top and is processed first.

If you swap the two if blocks, the program still uses LIFO, but the branch priority order changes. “Using a stack” does not by itself decide whether left or right is visited first; the push order is also an algorithmic decision.

### 10.4. This is a tree, not a general graph traversal

The example data is a finite tree with no cycles and no child nodes shared across multiple paths. Therefore, no visited set is needed.

For a graph with cycles or multiple paths to the same vertex, simply switching Deque between FIFO and LIFO is not enough for a correct algorithm: you need an appropriate marking and cycle-avoidance policy.

Do not apply the tree code template as-is to cyclic data and conclude that Deque is broken when the program does not terminate.

### 10.5. Cost of the two patterns

With n nodes, each node in the example tree is added, removed, and recorded once, so time is O(n) when head/tail operations have appropriate amortized cost.

The pending portion has different characteristics:

- Breadth-first may have to hold many nodes on a single level; pending memory depends on the tree's width.
- Depth-first on a binary tree holds the current path and pending branches; there is a bound based on tree height for this implementation style.
- The result list also holds n names, so the result itself requires O(n) memory.

Do not ignore result memory when analyzing the whole program. Deque is only the part coordinating pending work.

## 11. Choose FIFO or LIFO by requirement, not by habit

Some common pairings:

| Requirement | Policy to consider | Reason |
|---|---|---|
| Process tasks in waiting order | FIFO | Work that waited earlier is retrieved first |
| Level-by-level traversal | FIFO | Earlier discovered nodes stay ahead |
| Undo the most recent action | LIFO | Later actions need to be reversed first |
| Depth-first traversal with an explicit structure | LIFO | Continue along the branch just chosen |
| Restore nested structures | LIFO | The innermost nesting level is usually closed first |

Deque only keeps element order. For example, using it for undo does not automatically make an action reversible. Each element must carry enough information to perform the reverse business action.

FIFO also does not automatically provide data durability, completion acknowledgment, or cross-process work delivery. An in-memory ArrayDeque does not become an external queuing system just because the variable is named jobs.

In an algorithm, changing FIFO to LIFO can change the very meaning of the result. Identify why a particular pending element should be processed next, and then choose the corresponding pair of operations.

### 11.1. Do not mix roles on the same sequence without rules

If one part of the code calls offerLast to maintain FIFO while another pushes at the head, pushed tasks can jump ahead of already waiting tasks. That might be a valid priority requirement, but it is then no longer pure FIFO by insertion time.

If one part of the code uses the first end as the top while another removes from last, the stack state can be consumed opposite to expectations.

Keep the Deque within a clear ownership scope, name it after its role, and expose consistent business operations. Using the Queue type for a part that only needs FIFO also reduces the chance of calling the wrong end through that reference.

### 11.2. Do not use printing the Deque as a substitute for defining order

ArrayDeque is iterated from first to last. For a stack using first as the top, the iterator walks from top to bottom.

However, a for-each loop only reads; it does not pop. Printing in the expected order does not prove the processing loop actually removes from the right end or removes elements after processing.

Verify the actual sequence retrieved by poll/pop, especially when the algorithm adds more elements while processing.

## 12. Common mistakes when using Deque

| Practice | Consequence or confusion | Fix |
|---|---|---|
| Want FIFO but use addLast and pollLast | Retrieves newest first, becoming LIFO | Remove from the opposite end |
| Want LIFO but push then removeLast | Retrieves the oldest element at the bottom | Use pop or pollFirst per your emptiness policy |
| Use peek in a loop without removing | May process the same element forever | Use poll/pop when consumption is needed |
| Use pop when empty is normal | Unnecessary exception handling | Use pollFirst or an appropriate condition |
| Use poll when empty is an error without checking | May silently ignore a broken assumption | Handle null or use a throwing method |
| Offer null and expect false | ArrayDeque throws NullPointerException | Define non-null data |
| Treat initial capacity as a limit | Deque still grows and holds more data | Choose a real bounding mechanism |
| Assume every Queue is FIFO | Priority implementations have different policies | Read the contract of the class in use |
| Push left then right while wanting left first | Right is retrieved first because it is on top | Push in reverse order |
| Call remove(x) thinking it removes the head | That searches and removes by value | Distinguish remove() from remove(Object) |
| Pop inside a for-each loop on the same Deque | May cause the iterator to detect modification | Use a direct removal loop |
| Share ArrayDeque across threads without coordination | Correct ends still do not guarantee consistency | Choose an appropriate concurrency mechanism |

A simple trap worth checking is this loop:

```java
// Buggy snippet if no step removes or changes the head.
while (jobs.peekFirst() != null) {
    process(jobs.peekFirst());
}
```

If process does not remove from or modify the sequence, the same head task will be processed forever. “Reading an element” and “having consumed an element” are two different states.

The FIFO consumption pattern with ArrayDeque is to retrieve with pollFirst, check the result, and then process that retrieved value. Do not peek again and hope it is always the same element in any data-sharing context.

## 13. Test ordering with scenarios that expose wrong-end bugs

A test with only one element cannot distinguish FIFO from LIFO. With a single A, both retrieve A.

You should include at least the following scenarios:

### 13.1. Three distinct elements

```text
add A, B, C

FIFO must retrieve: A, B, C
LIFO must retrieve: C, B, A
```

This is the most basic test for choosing insertion/removal ends.

### 13.2. Interleaved insertions and removals

FIFO:

```text
add A
add B
remove -> A
add C
remove next -> B, C
```

LIFO:

```text
push A
push B
pop -> B
push C
pop next -> C, A
```

Interleaved cases help catch code that only works when all items are added before any are removed.

### 13.3. Empty, single-element, and duplicate elements

Check explicitly:

- When empty, should a null-returning or exception-throwing method be used?
- Does peek keep size unchanged?
- Does poll/pop remove exactly one element?
- Are two insertions of the same value kept as two occurrences?
- After draining completely and adding again, is the order still right?
- Where is null handled in the input contract?

Do not use a Set to verify output when order or occurrence count must be preserved; a Set can hide both kinds of bugs.

### 13.4. Comparing observable data

ArrayDeque does not provide sequence-based equals like List. Two ArrayDeque instances with the same elements do not by default return true for equals.

When you need to compare order, you can collect retrieved elements into a List as in Program 1, or build a List from the iterator to check the readable sequence. Those two approaches check two different things: one protects the consumption process, while the other only checks the current iteration order.

Also, do not use a single runtime timing value from a small example as a pass/fail criterion for FIFO/LIFO. This is an ordering contract, which can be tested directly with clear data.

## 14. Practice exercises

### Exercise 1: identify the policy

Call `addLast(A)`, `addLast(B)`, `addLast(C)` in sequence, then repeatedly call `pollLast()`.

What is the output, and is this FIFO?

**Suggested answer:** C, B, A; this is LIFO because adding and removing happen at the same end.

### Exercise 2: change emptiness handling while keeping LIFO

A stack uses push. You want the retrieval operation to return null when empty instead of throwing an exception.

Which method should you use?

**Suggested answer:** pollFirst. The top of push is at first, so changing the error policy must not also change the removal end.

### Exercise 3: only inspect the next task

A queue uses offerLast/pollFirst. You need to see the next task to be processed without removing it.

**Suggested answer:** peekFirst or peek. If you are certain it cannot be empty and want a clear error when that assumption is violated, you can use getFirst or element.

### Exercise 4: three child nodes by priority

You want a stack to process child nodes in the order X, Y, Z. In what order must you push them?

**Suggested answer:** Z, Y, X, so that X is pushed last and sits on top.

### Exercise 5: null and offer

Since offer returns a boolean, can you pass null into ArrayDeque and use false to signal invalid data?

**Suggested answer:** no. ArrayDeque does not accept null, and offering null throws NullPointerException. A boolean does not replace an input contract.

### Exercise 6: bounding a queue

Does initializing `new ArrayDeque<>(100)` guarantee rejecting the 101st task?

**Suggested answer:** no. That is the prepared initial capacity, not a fixed limit. You need an appropriate bounded structure or mechanism.

### Exercise 7: breadth-first or depth-first?

In the example tree, after A you want to process B then C before reaching D. Should you keep the pending buffer as FIFO or LIFO?

**Suggested answer:** FIFO, because nodes on the same level that entered the buffer earlier must be retrieved before nodes on the next level.

### Exercise 8: a misleading test result

A program retrieves all of A, B, and C, but the result is C, B, A when FIFO is required. A check using Set still passes.

What is wrong?

**Suggested answer:** the check discarded the order. You need to compare the output sequence, not just the set of members.

When using Deque in an algorithm, explicitly note the insertion end, removal end, and empty behavior. Those three decisions directly connect the FIFO/LIFO requirement to each API call and help keep processing rules stable as the code evolves.
