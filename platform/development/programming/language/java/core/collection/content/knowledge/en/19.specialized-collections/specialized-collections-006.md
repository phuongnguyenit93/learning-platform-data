# Vector and Stack: Legacy Contracts and Alternatives

Vector and Stack still appear in libraries, legacy interfaces, and long-lived Java codebases. Understanding them helps you read existing behavior accurately and choose the right data structure when writing new code or migrating old code.

You should not merely rename the classes. Vector is a List with specific synchronization characteristics and a historical API. Stack extends Vector, adding last-in, first-out (LIFO) usage while still carrying all of the list operations. Replacing them can change iteration order, empty-state handling, null support, and synchronization scope.

This article uses Java 17. "Legacy" here refers to design history and API direction; it does not mean the two classes have disappeared or must be rewritten on sight.

## 1. Two Abstractions to Distinguish

### 1.1. Indexed List

Vector is a resizable array of objects accessed by index. It implements List, so it has list semantics: it preserves element order, allows duplicates, and supports positional access.

A Vector object can be used as follows:

~~~java
List<String> names = new Vector<>();
names.add("A");
names.add("B");
String first = names.get(0);
~~~

This is a partial illustration. Using the List variable type expresses the list requirement, even though the concrete object is still a Vector.

### 1.2. Last-In, First-Out Stack

A stack is a discipline of operations: elements are added at the top and removed from the same top. When pushing A, B, and C in order, the pop order is C, B, A.

~~~text
push A, then B, then C

top    -> C
          B
bottom -> A

pop: C, B, A
~~~

Stack extends Vector to provide push, pop, peek, empty, and search. The Java documentation recommends using Deque and its implementations for a new stack's set of operations. [Java 17: Stack](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Stack.html)

The requirement for an "indexed list" and a "stack operating only at the top" are not the same contract. This is the starting point for choosing a replacement.

## 2. What Contracts Does Vector Carry?

Vector has existed since Java 1.0 and was retrofitted into the Java Collections Framework by implementing List in later versions. As a result, it has both historical method names and List interface method names.

### 2.1. Legacy Names and Their List Equivalents

| Legacy API | Equivalent List API by Purpose | Points to Note |
|---|---|---|
| addElement(x) | add(x) | addElement returns void; add returns boolean |
| elementAt(i) | get(i) | Reads by index |
| insertElementAt(x, i) | add(i, x) | Parameter order differs |
| setElementAt(x, i) | set(i, x) | set returns the old value; legacy API returns void |
| removeElement(x) | remove(Object) | Removes by object |
| removeElementAt(i) | remove(i) | Removes by index; different return type |
| removeAllElements() | clear() | Removes all elements |

The table describes operational intent; it does not guarantee that you can swap method names in every expression while ignoring return types or error handling.

With `List<Integer>`, `remove(i)` is also easily confused between removing by index and removing an Integer value. That is why you must check parameter types, not just method names.

### 2.2. Size vs. Capacity

Size is the actual number of elements. Capacity is the storage capacity of the backing array, which is at least equal to size.

`ensureCapacity(n)` prepares storage capacity without adding n elements. Conversely, `setSize(n)` changes the element count: increasing size appends null elements; decreasing size discards elements from the end.

Example:

~~~text
initially has A, B: size = 2
ensureCapacity(8): still has A, B
setSize(4): A, B, null, null
~~~

Do not use `setSize` merely to "preallocate memory." The newly added nulls become list elements and can affect processing or migration to a structure that forbids nulls.

Vector also has `capacityIncrement` and methods such as `trimToSize`. When replacing it, you must determine whether legacy code actually depends on those specific APIs or simply needs a List. [Java 17: Vector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Vector.html)

### 2.3. Synchronization Is Not Automatic Compound Atomicity

Vector is synchronized. However, multiple consecutive calls do not automatically become an indivisible operation.

Example:

~~~java
if (!values.contains(item)) {
    values.add(item);
}
~~~

This is an illustrative pattern that can fail a "add only if absent" requirement when multiple threads operate concurrently. Both threads can observe that the item is absent before either one adds it.

You must not infer that Vector's internal backing array is necessarily corrupted in that example. The problem is that the business condition spans multiple calls, while each individual call's lock scope does not cover both the check and the update.

## 3. Enumeration and Iterator: Reading Traversal Contracts

Vector provides `elements()`, which returns an Enumeration with `hasMoreElements`/`nextElement`. It also supports `Iterator` and `ListIterator` per the Collections Framework.

Iterator has a best-effort fail-fast mechanism. Vector's Enumeration is not fail-fast; if the Vector is structurally modified while an enumeration is active, the traversal results are undefined under that contract.

Therefore, do not switch from Iterator to Enumeration just to "stop getting ConcurrentModificationException." The absence of an exception does not prove that a traversal is seeing consistent data.

When a protected traversal is needed, the entire traversal scope must be organized under an appropriate locking policy. When a structurally separate snapshot is needed for processing outside the protected region, you can make a copy while the source is in a valid state.

A list copy still holds references to the elements; it does not automatically deep-copy the objects.

## 4. Stack: Stack Operations and Inherited Parts

### 4.1. Five Methods to Read Accurately

| Stack Method | Meaning |
|---|---|
| push(x) | Adds x at the top and returns x |
| pop() | Retrieves and removes the top; throws EmptyStackException if empty |
| peek() | Inspects the top without removing; throws EmptyStackException if empty |
| empty() | Checks whether there are no elements |
| search(x) | 1-based position from the top; returns -1 if not found |

`search` uses element equality and finds the occurrence closest to the top. It is not a 0-based List index.

For a Stack containing A, B, C in 0-based index order:

~~~text
indexOf(B) = 1
search(B)  = 2
peek()     = C
~~~

`search` and `indexOf` return two different kinds of coordinates. When migrating, never use a `search` result directly as a list access index. [Java 17: Stack methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Stack.html)

### 4.2. Stack Still Exposes Vector Operations

Because it extends Vector, Stack still has `add(index, value)`, `get`, `set`, `remove(index)`, `setSize`, and many other list operations.

Illustrative example:

~~~java
Stack<Integer> stack = new Stack<>();
stack.push(10);
stack.push(20);
stack.add(0, 99);
~~~

The data becomes 99, 10, 20. The indexed add modified the bottom; it is not a top-only operation of an abstract stack.

This does not break the rules of push/pop, but the API surface is broader than a LIFO requirement. Declaring with Deque expresses double-ended operations without carrying List's indexed-access API.

## 5. What to Replace Vector With?

### 5.1. Lists Not Requiring Internal Synchronization

For lists kept thread-local or governed by another clear access policy, `ArrayList` is usually the natural choice. The Vector documentation also points to ArrayList when Vector's synchronization implementation is not needed.

ArrayList retains indexing, ordering, and null support, but it is not self-synchronized. Do not swap it into multi-threaded shared code and accidentally remove a protection mechanism that legacy code relied upon. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

Converting with `new ArrayList<>(vector)` creates a new list in the source's iteration order. It does not alias the Vector structure, though the inner elements may still be the same object instances.

### 5.2. Shared Lists with Locking

`Collections.synchronizedList(new ArrayList<>())` provides a synchronized-wrapped List. Compound operations and traversals still require a policy covering the scope that needs consistency.

The documentation requires synchronizing on the wrapped list itself when traversing via iterator, spliterator, or stream; all accesses must go through the chosen mechanism. [Java 17: Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List))

It is not a magic transformation that makes every check-then-act snippet correct. If you switch from Vector to the wrapper just to rename the class while keeping the same compound-operation bug, the logic error remains.

### 5.3. Many Reads, Few Modifications

`CopyOnWriteArrayList` is an option to consider for certain shared lists where traversals vastly outnumber mutations. Mutating operations copy the backing array, while iterators see a snapshot at creation time and do not support modification through the iterator.

The trade-off is copying and memory cost on updates; it is not a suitable default for every multi-threaded list, especially under frequent write loads. [Java 17: CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

Choose based on workload and required observation contracts, not a generic "supports multithreading" label.

## 6. Replacing Stack with Deque: Choosing the Right End

### 6.1. Convention: Top at the Head of the Deque

Common approach:

~~~java
Deque<String> stack = new ArrayDeque<>();
stack.push("A");
stack.push("B");
String top = stack.pop();
~~~

`push` corresponds to `addFirst`; `pop` corresponds to `removeFirst`. When used consistently, the sequence above retrieves B first.

`ArrayDeque` is a resizable array implementation of Deque, is not self-synchronized, and does not allow null. Many operations at both ends have amortized constant-time cost; you do not need a `LinkedList` just because conceptual stack diagrams are often drawn with nodes. [Java 17: ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

### 6.2. Peek Does Not Have the Same Empty Contract

| Legacy Stack | With Deque, Top at Head | Difference to Preserve |
|---|---|---|
| push(x) | push(x), equivalent to addFirst(x) | Stack returns x; Deque.push returns void |
| pop() | pop() or removeFirst() | Empty: EmptyStackException changes to NoSuchElementException |
| peek() | peekFirst() or peek() | Deque returns null when empty |
| peek() when throwing on empty is desired | getFirst() | Throws NoSuchElementException, still different from the old exception type |
| empty() | isEmpty() | Same emptiness check intent |
| search(x) | No direct method with the same name and contract | Must determine whether position-from-top is truly needed |

Sharing the name `peek` is not enough to conclude the two methods are drop-in replacements everywhere. Code that catches `EmptyStackException` or uses `null` as valid data must be reviewed specifically. [Java 17: Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

### 6.3. Do Not Mix push with add Without Defining Semantics

On a Deque, `push` adds at the head, whereas `add` (from the Queue contract) adds at the tail. If code calls both out of a habit of thinking "both just add," it may no longer produce the intended LIFO sequence.

You can choose to place the top at the tail and use `addLast`/`removeLast`/`peekLast` consistently. However, once that convention is chosen, Deque's `push`/`pop` still operate at the head, not the tail.

Keeping one clear convention in the API of the class owning the data helps prevent callers from mixing the two styles of operations.

## 7. Migrating Stack Data to ArrayDeque Is More Than a Constructor Call

### 7.1. Iterator Order Differs from Stack Direction

After pushing A, B, C:

~~~text
Stack by index and iterator:   [A, B, C]
bottom                          A
top                                   C

ArrayDeque using push at head:
iterator:                      [C, B, A]
top                             C
~~~

Both can pop in C, B, A order, but their iterator orders differ.

If you create `new ArrayDeque<>(oldStack)`, the constructor ingests the source's iterator order, so the deque ends up with A at the head. Calling `pop` immediately retrieves A, reversing the pop semantics relative to `oldStack`.

### 7.2. Keeping the Top at the Head

Iterate the source from bottom to top and push each element:

~~~java
Deque<String> replacement = new ArrayDeque<>();
for (String item : oldStack) {
    replacement.push(item);
}
~~~

The resulting deque head is C, followed by B, A. Popping proceeds as C, B, A. The loop does not drain the source.

This example assumes a stable source containing no nulls. If legacy data contains nulls or concurrent modifications are occurring, those conditions must be handled before or within the migration policy; do not silently drop elements.

### 7.3. Keeping Bottom-First, Top-Last Representation

You can copy via the iterator:

~~~java
Deque<String> replacement = new ArrayDeque<>(oldStack);
String top = replacement.removeLast();
~~~

This approach retrieves C from the tail. Subsequent operations must consistently use the tail end. It is not equivalent to calling `Deque.pop` after the constructor.

Both approaches can be correct if the intent is clear. When migrating, verify the pop sequence, not just element counts or `toString` output.

### 7.4. The equals Contract Also Differs

Stack inherits List's content-and-order-based equality. `ArrayDeque` does not provide element-sequence-based `equals` like List; two distinct deque instances can contain the same elements and still return `false` for `equals`.

Do not convert content assertions to `deque.equals` and mistakenly think data was lost. If you want to compare a sequence in traversal order, build or compare the element sequence under an explicit contract; if you want to compare pop order, verify that exact order.

Similarly, do not swap objects used as hash map keys while ignoring `equals`/`hashCode` changes.

## 8. Per-Method Synchronization Is Not Enough for an Algorithm

### 8.1. Check-Then-Pop Can Still Fail

Problematic pattern:

~~~java
if (!shared.empty()) {
    shared.pop();
}
~~~

Both calls may be individually synchronized, yet the interleaving can still be:

~~~text
thread 1: sees non-empty
thread 2: sees non-empty
thread 1: pops the only element
thread 2: pops on an already-empty stack
~~~

No step requires an internal `pop` to be corrupted. Each `pop` executes properly on the state it observes. What is wrong is expecting the emptiness check to remain valid until the subsequent `pop`.

### 8.2. Protecting the Whole Compound Operation When Keeping Legacy Stack

One way to structure this in a shared-lock model:

~~~java
synchronized (shared) {
    if (!shared.empty()) {
        shared.pop();
    }
}
~~~

Other related operations must follow the same protection policy. Do not place `synchronized` in just one spot while letting other call paths bypass the business invariants that must hold.

The lock here illustrates the intended atomic scope. It is not a reason to keep `Stack` for all new code; data structure selection and operation design still need to be separated.

### 8.3. With Concurrent Structures, Prefer Purpose-Built Combined Operations

If using a concurrent deque that disallows null, `pollFirst` is a single operation that retrieves if present and returns null if empty. It avoids combining `isEmpty` then `pop` just to ask "take if available."

A sequence of multiple operations still does not automatically become a transaction just because each individual operation on the structure is thread-safe. For example, moving elements between two structures or checking a condition across multiple objects requires explicit design.

## 9. Choosing an Alternative by Requirement

| Requirement | Option to Consider |
|---|---|
| Thread-local List or no internal locking needed | ArrayList |
| Shared List with explicit locking policy | SynchronizedList or structure under a designed lock |
| Heavily traversed, rarely modified List needing snapshot iterators | CopyOnWriteArrayList |
| Unshared/non-contended stack, no nulls stored | Deque with ArrayDeque |
| Shared Deque, non-blocking operations | ConcurrentLinkedDeque |
| Deque coordinating waiting for elements or space | Appropriate BlockingDeque, such as LinkedBlockingDeque |
| External API strictly requires Vector/Stack | Maintain compatibility at the boundary and evaluate internal usage |

`ConcurrentLinkedDeque` provides concurrent operations, disallows null, and has weakly consistent iterators. It does not guarantee bulk operations are atomic, and `size` is not a constant-time count as you might be used to with lists. [Java 17: ConcurrentLinkedDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html)

`LinkedBlockingDeque` can be capacity-bounded. If waiting is needed, use the `put`/`take` family or appropriate timed operations; `push` does not automatically become a blocking call just because the object implements `BlockingDeque`. [Java 17: LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html)

Do not pick a structure with stronger mechanisms out of habit. You need to identify data shape, empty/null rules, read/write load, and how threads coordinate.

## 10. Compatibility Boundaries to Check Before Replacing

In legacy code, there may be APIs that accept or return concrete `Vector`, serialized data contracts, subclasses using `protected` fields, or callers depending on `Enumeration`. Changing internal variables to `List` does not automatically make all those boundaries compatible.

A sensible review process is:

1. Determine whether the code is using `List` semantics or truly needs `Vector`-specific APIs.
2. For `Stack`, document where the top is located and the pop order.
3. Check `null` data, empty-state exceptions, return values, and `search`.
4. Determine whether the iterator or display order is part of the contract.
5. Identify compound operations and concurrency policies.
6. Replace the structure within the understood scope, then verify the behavior that must be preserved.

This is a contract assessment, not a mandate to rewrite every legacy class immediately. Both classes may still need to be maintained at a specific compatibility boundary.

## 11. Complete Java Program

Save the following code to `LegacyCollectionsDemo.java`. The program uses separate data for each scenario so that pops do not interfere with other scenarios.

The two-thread section uses `CountDownLatch` so both threads complete the non-empty check before popping. It does not use `sleep` to guess scheduling. It only prints the summary after `join`, so stdout does not depend on which thread wins the element.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.EmptyStackException;
import java.util.Enumeration;
import java.util.List;
import java.util.Stack;
import java.util.Vector;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class LegacyCollectionsDemo {
    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected collection result");
        }
    }

    private static String exceptionName(Supplier<?> operation) {
        try {
            operation.get();
            return "none";
        } catch (RuntimeException exception) {
            return exception.getClass().getSimpleName();
        }
    }

    private static <E> List<E> drainFirst(Deque<E> deque) {
        List<E> result = new ArrayList<>();
        while (!deque.isEmpty()) {
            result.add(deque.removeFirst());
        }
        return result;
    }

    private static <E> List<E> drainLast(Deque<E> deque) {
        List<E> result = new ArrayList<>();
        while (!deque.isEmpty()) {
            result.add(deque.removeLast());
        }
        return result;
    }

    private static void awaitBoth(CountDownLatch latch) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Both checks did not complete");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new AssertionError(exception);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Vector<String> vector = new Vector<>(2);
        vector.addElement("A");
        vector.add("B");
        vector.ensureCapacity(8);
        require(vector.size() == 2 && vector.capacity() >= 8);
        System.out.println("vector/size=" + vector.size()
                + ", capacityAtLeast8=" + (vector.capacity() >= 8));
        vector.setSize(4);
        require(vector.size() == 4 && vector.get(2) == null);
        System.out.println("vector/afterSetSize=" + vector);
        List<String> copiedList = new ArrayList<>(vector);
        vector.removeElement("B");
        require(copiedList.size() == 4 && copiedList.get(1).equals("B"));
        System.out.println("vector/afterRemove=" + vector
                + ", arrayListCopy=" + copiedList);
        Enumeration<String> enumeration = vector.elements();
        List<String> enumerated = new ArrayList<>();
        while (enumeration.hasMoreElements()) {
            enumerated.add(enumeration.nextElement());
        }
        System.out.println("vector/enumeration=" + enumerated);

        Stack<String> legacy = new Stack<>();
        legacy.push("A");
        legacy.push("B");
        String pushed = legacy.push("C");
        require(pushed.equals("C") && legacy.search("B") == 2);
        System.out.println("stack/pushReturn=" + pushed
                + ", top=" + legacy.peek()
                + ", searchB=" + legacy.search("B")
                + ", indexB=" + legacy.indexOf("B")
                + ", missing=" + legacy.search("missing"));
        System.out.println("stack/iteration=" + new ArrayList<>(legacy));

        Deque<String> modern = new ArrayDeque<>();
        modern.push("A");
        modern.push("B");
        modern.push("C");
        System.out.println("deque/iteration=" + new ArrayList<>(modern));

        Stack<String> emptyStack = new Stack<>();
        Deque<String> emptyDeque = new ArrayDeque<>();
        System.out.println("empty/stackPop=" + exceptionName(emptyStack::pop)
                + ", dequePop=" + exceptionName(emptyDeque::pop));
        System.out.println("empty/stackPeek=" + exceptionName(emptyStack::peek)
                + ", dequePeek=" + emptyDeque.peek());

        Stack<String> nullable = new Stack<>();
        nullable.push(null);
        String nullFromStack = nullable.pop();
        boolean dequeNullRejected = false;
        try {
            modern.push(null);
        } catch (NullPointerException exception) {
            dequeNullRejected = true;
        }
        require(dequeNullRejected && nullFromStack == null);
        System.out.println("null/stackPop=" + nullFromStack
                + ", dequeRejected=" + dequeNullRejected);

        Stack<Integer> inherited = new Stack<>();
        inherited.push(10);
        inherited.push(20);
        inherited.add(0, 99);
        List<Integer> beforePop = new ArrayList<>(inherited);
        Integer inheritedPop = inherited.pop();
        require(beforePop.equals(List.of(99, 10, 20)) && inheritedPop == 20);
        System.out.println("inheritance/afterIndexedAdd=" + beforePop
                + ", pop=" + inheritedPop);

        Deque<String> naive = new ArrayDeque<>(legacy);
        System.out.println("migration/naivePop=" + naive.pop());
        Deque<String> topFirst = new ArrayDeque<>();
        for (String item : legacy) {
            topFirst.push(item);
        }
        Deque<String> topLast = new ArrayDeque<>(legacy);
        List<String> firstSequence = drainFirst(topFirst);
        List<String> lastSequence = drainLast(topLast);
        require(firstSequence.equals(List.of("C", "B", "A"))
                && lastSequence.equals(firstSequence));
        System.out.println("migration/topFirst=" + firstSequence);
        System.out.println("migration/topLast=" + lastSequence);
        System.out.println("migration/source=" + legacy);

        Stack<String> sameStack = new Stack<>();
        sameStack.addAll(legacy);
        Deque<String> dequeA = new ArrayDeque<>(legacy);
        Deque<String> dequeB = new ArrayDeque<>(legacy);
        require(legacy.equals(sameStack) && !dequeA.equals(dequeB));
        System.out.println("equals/stack=" + legacy.equals(sameStack)
                + ", arrayDeque=" + dequeA.equals(dequeB));

        Stack<String> shared = new Stack<>();
        shared.push("only");
        CountDownLatch bothChecked = new CountDownLatch(2);
        AtomicInteger successful = new AtomicInteger();
        AtomicInteger emptyFailures = new AtomicInteger();
        Runnable separateCalls = () -> {
            if (!shared.empty()) {
                bothChecked.countDown();
                awaitBoth(bothChecked);
                try {
                    shared.pop();
                    successful.incrementAndGet();
                } catch (EmptyStackException exception) {
                    emptyFailures.incrementAndGet();
                }
            }
        };
        Thread first = new Thread(separateCalls);
        Thread second = new Thread(separateCalls);
        first.start();
        second.start();
        first.join();
        second.join();
        require(successful.get() == 1 && emptyFailures.get() == 1
                && shared.empty());
        System.out.println("compound/methodsOnlyPops=" + successful.get()
                + ", emptyFailures=" + emptyFailures.get()
                + ", remaining=" + shared.size());

        Stack<String> protectedStack = new Stack<>();
        protectedStack.push("only");
        AtomicInteger protectedPops = new AtomicInteger();
        Runnable wholeOperation = () -> {
            synchronized (protectedStack) {
                if (!protectedStack.empty()) {
                    protectedStack.pop();
                    protectedPops.incrementAndGet();
                }
            }
        };
        Thread third = new Thread(wholeOperation);
        Thread fourth = new Thread(wholeOperation);
        third.start();
        fourth.start();
        third.join();
        fourth.join();
        require(protectedPops.get() == 1 && protectedStack.empty());
        System.out.println("compound/lockedPops=" + protectedPops.get()
                + ", remaining=" + protectedStack.size());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 LegacyCollectionsDemo.java
java LegacyCollectionsDemo
~~~

Stdout of the verification run:

~~~text
vector/size=2, capacityAtLeast8=true
vector/afterSetSize=[A, B, null, null]
vector/afterRemove=[A, null, null], arrayListCopy=[A, B, null, null]
vector/enumeration=[A, null, null]
stack/pushReturn=C, top=C, searchB=2, indexB=1, missing=-1
stack/iteration=[A, B, C]
deque/iteration=[C, B, A]
empty/stackPop=EmptyStackException, dequePop=NoSuchElementException
empty/stackPeek=EmptyStackException, dequePeek=null
null/stackPop=null, dequeRejected=true
inheritance/afterIndexedAdd=[99, 10, 20], pop=20
migration/naivePop=A
migration/topFirst=[C, B, A]
migration/topLast=[C, B, A]
migration/source=[A, B, C]
equals/stack=true, arrayDeque=false
compound/methodsOnlyPops=1, emptyFailures=1, remaining=0
compound/lockedPops=1, remaining=0
~~~

The code was compiled with `--release 17` and ran successfully. The release option specifies the API level and compatible target bytecode; it does not assert that the executing JVM itself is JDK 17.

## 12. Explanation of Result Groups

### 12.1. Vector and List Copy

`ensureCapacity` keeps `size` at two; `setSize` increases it to four and appends two nulls. `arrayListCopy` was created before the source removed B, so it still retains the original four elements.

`Enumeration` is used when the data does not change during traversal. This article does not use that result to guarantee anything when the source is modified concurrently.

### 12.2. Stack and Ordering

`Stack` returns C from `push`, peeks C, and reports `search("B")` as two while `indexOf("B")` is one. `Stack`'s iterator traverses A, B, C; the deque built with `push` traverses C, B, A.

Inserting 99 at index 0 of `Stack` demonstrates that inherited `Vector` operations are still present. `pop` still retrieves 20 from the top after that operation.

### 12.3. Emptiness, Null, and Migration

`emptyStackPop` and `emptyDequePop` yield two different exception names. `peek` on an empty `Stack` throws an exception, whereas `Deque.peek` returns null.

`Stack` can hold and pop `null` in the example. `ArrayDeque` rejects pushing `null`. This is a data contract change that must be identified during migration.

`naivePop` retrieves A because the constructor copies `Stack`'s bottom-first order. Both intentional approaches retrieve C, B, A and do not drain the source. Verification does not stop at merely having the same three elements.

### 12.4. Equals

Two separate `Stack` instances with the same element sequence are equal according to `List`. Two separate `ArrayDeque` instances with the same element sequence are not equal according to the class's `equals`.

The program checks the popped sequence using the resulting `List` when content equality is needed; it does not use `deque.equals` for that task.

### 12.5. Compound Operations

When relying solely on `Stack`'s per-call synchronization, one thread retrieves the element and the other encounters `EmptyStackException` after both have seen it was non-empty.

When holding the lock across both the check and the `pop`, only one thread pops; the subsequent thread sees it is empty and skips it. This result demonstrates the protection scope of a compound operation, not a performance benchmark or a simulation of an entire concurrent system.

## 13. Common Pitfalls

| Pitfall | Correct Understanding |
|---|---|
| Legacy Vector means it has been removed from Java | It still exists; you need to understand compatibility reasons and newer API direction |
| Per-method synchronized makes every algorithm atomic | Check-then-update sequences need their own scope |
| SetSize only reserves capacity | It changes the element count and can append null |
| Enumeration does not throw CME so it is safe during modification | Not being fail-fast does not mean consistent traversal |
| Stack only allows operations at the top | It also inherits many List operations from Vector |
| Search returns a 0-based index | It returns a 1-based distance from the top |
| Stack.push and Deque.push have the same return type | Stack returns the element; Deque.push returns void |
| Both classes' peek have the same empty behavior | Stack throws an error; Deque.peek returns null |
| ArrayDeque preserves all null data from Stack | ArrayDeque forbids null |
| New ArrayDeque from Stack then pop always preserves old LIFO | You must check iterator direction and the pop end |
| Mixing add and push does not change order | add appends at tail, push prepends at head on Deque |
| Deque.equals compares contents like Stack | ArrayDeque has no List-based equals |
| Switching to ArrayList automatically keeps Vector's synchronization | ArrayList is not self-synchronized |
| BlockingDeque.push always waits when full | Waiting depends on the specific method chosen |
| Concurrent structures make multiple operations transactional | Invariants spanning multiple steps still require explicit design |

## 14. Practice Exercises and Solutions

### Exercise 1. Size or Capacity?

A `Vector` has two elements. Call `ensureCapacity(100)`, then `setSize(5)`. What is the element count after each step, and what do the new positions contain?

**Solution:** After `ensureCapacity`, it is still two. After `setSize`, it is five, and the three new positions are `null`. The two operations have different purposes.

### Exercise 2. Search and Index

A `Stack` has A, B, C pushed onto it. What do `search("A")` and `indexOf("A")` return? If another A is at the top, which occurrence does `search("A")` choose?

**Solution:** Initially `search("A")` is three, and `indexOf("A")` is zero. If there is an A at the top, `search("A")` is one because it chooses the occurrence closest to the top.

### Exercise 3. Changing peek

Legacy code catches `EmptyStackException` from `peek` when there is no data. Does switching to `ArrayDeque.peek` preserve that behavior? How does `getFirst` differ?

**Solution:** No. Deque's `peek` returns `null`. `getFirst` throws `NoSuchElementException` when empty, which is still not the same exception type as `Stack`. You must choose and update the empty-reporting policy according to the desired contract.

### Exercise 4. Migrating Contents

A `Stack` has A, B, C in iterator order. Creating a `new ArrayDeque` from the source and calling `pop` retrieves what? State two conventions to preserve the C, B, A pop order.

**Solution:** `pop` retrieves A. You can iterate the `Stack` and `push` each element into a new deque so the top is at the head, or copy via the iterator and use `removeLast`/`addLast`/`peekLast` with the top at the tail. Do not mix conventions.

### Exercise 5. Why Do Two Threads Still Fail?

A `Stack` has one element; both threads run `empty` then `pop` without a lock covering the whole sequence. All methods are synchronized. Where can the failure occur?

**Solution:** Both check non-empty before either pops. The first thread takes the element; the second thread pops on an empty stack. Each individual call is correct, but the checked condition is not held until the update. You need a protected compound operation or a purpose-built combined API on an appropriate structure.

### Exercise 6. Null During Replacement

Legacy `Stack` data contains `null` as a valid element. Can you switch directly to `ArrayDeque` and skip `null` during copying?

**Solution:** That cannot be called a behavior-preserving migration. `ArrayDeque` does not accept `null`; silently dropping it alters the data and can change ordering or task counts. You must determine an appropriate data representation and an explicit migration policy.

### Exercise 7. Choosing a Shared List

A list has very many traversals and very few updates. Why is `CopyOnWriteArrayList` worth considering, yet not the default choice for every write workload?

**Solution:** Snapshot iterators allow traversal without subsequent structural updates interfering with the array being iterated. In return, every mutating operation creates a new array; frequent writes can cause significant copying and memory overhead.

### Exercise 8. Comparing After Migration

A test previously used `Stack.equals` to compare two sequences. After replacing with `ArrayDeque`, `equals` returns `false` even though the elements print identically. Is that enough to conclude the data migration failed?

**Solution:** No. `ArrayDeque` does not have `List`-based content `equals`. You need to compare the element sequences in the order that must be preserved, especially the pop order if it is a stack.

## 15. Making Replacement Decisions Based on Contracts

Determine whether you need a `List` or LIFO, whether `null` is allowed, how emptiness is reported, what traversal direction means, and whether there are compound operations across multiple threads.

`ArrayList` and `ArrayDeque` express many modern requirements more clearly, while concurrent structures provide different coordination contracts. Understanding what is currently relied upon is what allows you to replace `Vector` or `Stack` without unintended behavior changes.
