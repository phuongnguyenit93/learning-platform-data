# The add–offer, remove–poll, and element–peek Pairs

## 1. Three Operations, Two Ways to Report Failure

A queue stores elements before they are processed. When using one, you typically need three operations: inserting an element, removing an element, or merely inspecting the element about to be removed.

Each operation has two corresponding methods in `Queue`. When the operation can be performed, the methods in the same pair serve an equivalent purpose. They differ most clearly when the queue is full or empty:

- `add(e)` and `offer(e)` are used to insert.
- `remove()` and `poll()` are used to retrieve and remove.
- `element()` and `peek()` are used to inspect while keeping the element in place.

One side reports an unperformable operation with an exception; the other uses a special value, `false` or `null`. However, that does not mean every data error in `offer` is turned into `false`.

This lesson explains each pair, verifies empty queues and capacity-bounded queues, and clarifies common misconceptions about `null`, ordering, and the `remove` method with an argument. The complete code uses APIs available in Java 17.

You need to know variables, method calls, conditionals, and loops. How to read the `Queue<String>` type, return values, and key exceptions are introduced in place.

## 2. Queue, the Head, and Implementation Classes

`Queue<E>` is an interface, where `E` is the element type. For example:

~~~java
Queue<String> pending = new ArrayDeque<>();
~~~

This is an illustrative declaration; you need to import `java.util.Queue` and `java.util.ArrayDeque` when placing it in a program.

`Queue<String>` indicates that the code is working with the string queue contract. `ArrayDeque` is the concrete class providing the object behind the variable. You can call `Queue` operations through the `pending` variable without needing to know the internal array details.

The **head** of the queue is the element that `remove()` or `poll()` will retrieve. `element()` and `peek()` also observe this same head, without removing it.

In a FIFO queue — first-in, first-out — new elements are typically added at the tail, while removal happens at the head:

~~~text
remove ← head [A, B, C] tail ← add

A is removed before B, B before C.
~~~

The method names alone do not guarantee that every implementation class is FIFO. For example, `PriorityQueue` chooses its head by priority. Therefore, before predicting which element will be returned, you must know the ordering rule of the class being used. [Java 17: Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

## 3. Contract Table of the Six Methods

For a modifiable queue and valid data:

| Purpose | Throws Exception | Returns Special Value | On Success |
| --- | --- | --- | --- |
| Insert an element | `add(e)` | `offer(e)` | Inserts the element and returns `true` |
| Remove the head | `remove()` | `poll()` | Returns the head element and removes it |
| Inspect the head | `element()` | `peek()` | Returns the head element without removing it |

Failure scenarios need to be read separately:

| Scenario | Method | Result |
| --- | --- | --- |
| Out of space due to capacity limit | `add(e)` | `IllegalStateException` |
| Out of space due to capacity limit | `offer(e)` | `false` |
| No element to remove | `remove()` | `NoSuchElementException` |
| No element to remove | `poll()` | `null` |
| No element to inspect | `element()` | `NoSuchElementException` |
| No element to inspect | `peek()` | `null` |

`add` and `offer` return `boolean`, while the four read/remove methods return an element of type `E`. Do not read `poll` as an operation that merely answers whether removal succeeded: it returns the actual element that was just removed.

"Returns special value" only refers to the corresponding full or empty scenario. Other contract violations, such as inserting `null` into a class that forbids `null`, may still throw an exception.

## 4. add and offer: Same Insertion, Different Full-Queue Reporting

For a FIFO queue currently containing `[A]` with space available:

~~~text
add(B)   → true; queue becomes [A, B]
~~~

If replaced with `offer(B)` on the same initial state, insertion also succeeds and returns `true`.

It is not the case that `add` inserts at the head while `offer` inserts at the tail. The insertion position is determined by the implementation class's contract; the two names in the pair do not signify two different directions.

The observable difference appears when the queue has a fixed capacity. For example, an `ArrayBlockingQueue` created with capacity 2:

~~~java
Queue<String> bounded = new ArrayBlockingQueue<>(2);
~~~

After adding A and B, there is no room for C:

~~~text
offer(C) → false
add(C)   → IllegalStateException
~~~

C is not added in either case above. The queue still contains `[A, B]`. `offer` does not silently replace A with C, nor does it automatically evict an older element to make room.

When A is removed, the queue has B remaining and an open slot. A new `offer(C)` call can succeed, producing `[B, C]`. This is a new insertion operation at a later time, not the previously rejected `offer` waiting in the background.

`ArrayBlockingQueue` is a fixed-capacity queue. The program in this lesson uses it to create a full-queue scenario deterministically, without spawning additional threads or waiting. [Java 17: ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

## 5. When offer Returns false, the Program Must Decide What Comes Next

Choose `offer` when running out of queue capacity is a situation that the calling code should handle through normal control flow. For example, a request-receiving method might return a "not accepted" result to the sender.

If you ignore the return value:

~~~java
// Illustrates ignoring the result; does not prove the element was accepted.
pending.offer("job-3");
~~~

you do not know whether the element entered the queue or was rejected. No exception does not mean insertion succeeded.

An illustrative method that clearly expresses whether an item was accepted:

~~~java
static boolean trySubmit(Queue<String> pending, String job) {
    return pending.offer(job);
}
~~~

This is a method to place inside a class, assuming the queue's policy and input data are already defined. The caller still must use the result, such as reporting non-acceptance or executing a controlled retry policy.

`true` only confirms that the element was inserted by the queue operation. It does not prove that the job has finished processing, that the result has been saved, or that another actor cannot immediately remove the element right afterward.

Choose `add` when failing to insert due to capacity represents an abnormal condition that the code's contract wants to report with an exception. There is no rule that `offer` is always right and `add` is always wrong; the choice must match what a full queue means to the caller.

Also, do not use a loop that keeps retrying `offer` without a stopping condition just to avoid dealing with `false`. If you need to wait for space, explicitly choose an appropriate API and waiting policy rather than turning an immediate operation into a resource-consuming loop.

## 6. offer Does Not Mean "Never Throws an Exception"

An `ArrayDeque` does not accept `null` elements. Both:

~~~java
pending.add(null);
pending.offer(null);
~~~

throw `NullPointerException` if `pending` refers to an `ArrayDeque`. The two lines above illustrate individual calls separately, not two statements to run sequentially without error handling.

`false` from `offer` is not meant to serve as a catch-all code for every programming error. An element type not accepted by the implementation class, or an element property that violates that class's constraints, can also lead to an appropriate exception.

For `PriorityQueue`, elements must also be comparable according to the rule the queue uses. Switching from `add` to `offer` does not magically create an ordering for incomparable objects.

The practical rule is to separate:

- **Cannot insert right now due to capacity:** handle the result of `offer` or the exception from `add`.
- **Element violates the input contract:** fix/validate the data or handle the error according to the program's contract.

Do not wrap everything in `catch (Exception)` and treat it all as "queue full." That approach blurs data errors with out-of-space conditions.

## 7. remove() and poll(): Both Retrieve and Remove the Head

For a FIFO queue currently containing `[A, B]`:

~~~text
remove() → returns A; remaining [B]
~~~

If `poll()` is used on the same initial state, it also returns A and leaves B.

Both remove the returned element. There is no need to call `remove` again after `poll` succeeds. If you do, you may accidentally remove the next element.

When the queue is empty:

~~~text
remove() → NoSuchElementException
poll()   → null
~~~

Choose `poll` when running out of elements is an expected outcome, such as a processing pass that drains whatever is currently available. Choose `remove` when the code's contract requires an element to be present and being empty signals a violated assumption that should be reported explicitly.

With a queue specified not to contain `null`, you can write:

~~~java
String next = pending.poll();
if (next != null) {
    System.out.println("Received: " + next);
}
~~~

This is an illustrative snippet with an already-declared `pending` variable. If `next` is non-null, the element has already left the queue before the print statement runs. If subsequent processing fails, `Queue` does not automatically put it back.

Do not immediately assign the result of `poll` to a primitive variable such as `int` if the queue can be empty. A `null` `Integer` result will cause an unboxing error before you can check for the absence of data.

## 8. element and peek: Inspect Only, Do Not Remove

For a stable queue `[A, B]`:

~~~text
element() → A; queue remains [A, B]
peek()    → A; queue remains [A, B]
~~~

If no other operation modifies the data, calling them again will still inspect A. These two methods do not mark "A as processed" and do not promote B to the head.

When empty:

~~~text
element() → NoSuchElementException
peek()    → null
~~~

A common mistake is using `peek` as both the loop condition and the processing operation, without ever removing:

~~~java
// Illustrates a bug: if the queue does not change, the head element is read repeatedly.
while (pending.peek() != null) {
    System.out.println(pending.peek());
}
~~~

This snippet is unsuitable for draining data; on a non-empty queue that is not modified, it never advances to the next element. Use `poll` to retrieve and remove, or use an iterator if you only want to read each element once according to the class's iteration policy.

`peek` also does not reserve or hold the element for the reader. A `peek` followed later by a `poll` are two separate calls. If other code or another thread intervenes to modify the queue, you must not assume those two calls refer to the same element.

## 9. Complete Program Verifying the Six Methods

Save the code as `QueueMethodPairsDemo.java`. The example uses:

- `ArrayDeque` for basic FIFO operations and the null-forbidding policy.
- `ArrayBlockingQueue` with capacity 2 to verify running out of space.
- `LinkedList` to expose the ambiguity when `null` is allowed in a `Queue`.
- `PriorityQueue` to distinguish a priority-based head from an arrival-order head.
- `Deque` to relate the method names.

The `drainNonNullQueue` method states its data precondition clearly in its name: the queue does not store `null`. The program only calls it with `PriorityQueue`, a class that forbids `null`.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.PriorityQueue;
import java.util.Queue;
import java.util.concurrent.ArrayBlockingQueue;

public class QueueMethodPairsDemo {
    static <E> List<E> drainNonNullQueue(Queue<E> queue) {
        List<E> values = new ArrayList<>();
        E value;
        while ((value = queue.poll()) != null) {
            values.add(value);
        }
        return values;
    }

    public static void main(String[] args) {
        Queue<String> fifo = new ArrayDeque<>();
        System.out.println("fifo add A=" + fifo.add("A"));
        System.out.println("fifo offer B=" + fifo.offer("B"));
        System.out.println("fifo=" + fifo);
        System.out.println("peek=" + fifo.peek());
        System.out.println("element=" + fifo.element());
        System.out.println("after inspection=" + fifo);
        System.out.println("poll=" + fifo.poll());
        System.out.println("after poll=" + fifo);
        System.out.println("remove=" + fifo.remove());
        System.out.println("after remove=" + fifo);
        System.out.println("empty poll=" + fifo.poll());
        System.out.println("empty peek=" + fifo.peek());
        try {
            fifo.remove();
        } catch (NoSuchElementException exception) {
            System.out.println("empty remove=" + exception.getClass().getSimpleName());
        }
        try {
            fifo.element();
        } catch (NoSuchElementException exception) {
            System.out.println("empty element=" + exception.getClass().getSimpleName());
        }

        Queue<String> bounded = new ArrayBlockingQueue<>(2);
        System.out.println("bounded offer A=" + bounded.offer("A"));
        System.out.println("bounded add B=" + bounded.add("B"));
        System.out.println("bounded full offer C=" + bounded.offer("C"));
        System.out.println("bounded after rejected offer=" + bounded);
        try {
            bounded.add("C");
        } catch (IllegalStateException exception) {
            System.out.println("bounded full add=" + exception.getClass().getSimpleName());
        }
        System.out.println("bounded after rejected add=" + bounded);
        System.out.println("bounded poll=" + bounded.poll());
        System.out.println("bounded retry offer C=" + bounded.offer("C"));
        System.out.println("bounded remaining=" + bounded);

        Queue<Integer> growing = new ArrayDeque<>(1);
        System.out.println("growing offers="
                + growing.offer(1) + "/" + growing.offer(2) + "/" + growing.offer(3));
        System.out.println("growing size=" + growing.size());

        Queue<String> noNull = new ArrayDeque<>();
        try {
            noNull.offer(null);
        } catch (NullPointerException exception) {
            System.out.println("offer null=" + exception.getClass().getSimpleName());
        }
        try {
            noNull.add(null);
        } catch (NullPointerException exception) {
            System.out.println("add null=" + exception.getClass().getSimpleName());
        }
        System.out.println("after invalid inserts size=" + noNull.size());

        Queue<String> permissive = new LinkedList<>();
        permissive.offer(null);
        permissive.offer("tail");
        System.out.println("nullable peek=" + permissive.peek());
        System.out.println("nullable size after peek=" + permissive.size());
        System.out.println("nullable poll=" + permissive.poll());
        System.out.println("nullable empty after poll=" + permissive.isEmpty());
        System.out.println("nullable remaining=" + permissive);

        Queue<String> named =
                new ArrayDeque<>(List.of("head", "middle", "tail"));
        System.out.println("remove middle=" + named.remove("middle"));
        System.out.println("after value remove=" + named);
        System.out.println("remove head=" + named.remove());
        System.out.println("remove missing=" + named.remove("missing"));
        System.out.println("after both removals=" + named);

        Queue<Integer> priority = new PriorityQueue<>();
        priority.addAll(List.of(7, 2, 5, 2));
        System.out.println("priority size=" + priority.size());
        System.out.println("priority peek=" + priority.peek());
        System.out.println("priority remove=" + priority.remove());
        System.out.println("priority poll=" + priority.poll());
        System.out.println("priority drain=" + drainNonNullQueue(priority));
        System.out.println("priority empty=" + priority.isEmpty());

        Deque<String> deque = new ArrayDeque<>();
        Queue<String> sameObject = deque;
        sameObject.offer("first");
        deque.offerLast("second");
        System.out.println("queue peek/deque peekFirst="
                + sameObject.peek() + "/" + deque.peekFirst());
        System.out.println("queue remove=" + sameObject.remove());
        System.out.println("deque pollFirst=" + deque.pollFirst());
        System.out.println("deque empty=" + deque.isEmpty());
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 QueueMethodPairsDemo.java
java QueueMethodPairsDemo
~~~

Use JDK 17 or later. The `--release 17` option checks code and APIs against Java 17. The filename matches the `public` class.

Expected output:

~~~text
fifo add A=true
fifo offer B=true
fifo=[A, B]
peek=A
element=A
after inspection=[A, B]
poll=A
after poll=[B]
remove=B
after remove=[]
empty poll=null
empty peek=null
empty remove=NoSuchElementException
empty element=NoSuchElementException
bounded offer A=true
bounded add B=true
bounded full offer C=false
bounded after rejected offer=[A, B]
bounded full add=IllegalStateException
bounded after rejected add=[A, B]
bounded poll=A
bounded retry offer C=true
bounded remaining=[B, C]
growing offers=true/true/true
growing size=3
offer null=NullPointerException
add null=NullPointerException
after invalid inserts size=0
nullable peek=null
nullable size after peek=2
nullable poll=null
nullable empty after poll=false
nullable remaining=[tail]
remove middle=true
after value remove=[head, tail]
remove head=head
remove missing=false
after both removals=[tail]
priority size=4
priority peek=2
priority remove=2
priority poll=2
priority drain=[5, 7]
priority empty=true
queue peek/deque peekFirst=first/first
queue remove=first
deque pollFirst=second
deque empty=true
~~~

## 10. Reading the Output by Pair

### 10.1. Success Does Not Expose Differences in Error Reporting

`fifo add A=true` and `fifo offer B=true` show that both insertions succeeded. The FIFO queue is `[A, B]`.

`peek=A` and `element=A` appear alongside `after inspection=[A, B]`. This is evidence that the inspection pair does not remove.

`poll=A` leaves B; `remove=B` empties the queue. Each operation in the removal pair removed exactly one element.

### 10.2. Empty Queues Separate the Two Result Styles

`empty poll=null` and `empty peek=null` use the special value. `empty remove=NoSuchElementException` and `empty element=NoSuchElementException` use an exception.

The `try/catch` blocks in the program catch the exact errors being demonstrated so that later examples can continue. They do not turn every exception raised elsewhere into an empty result.

### 10.3. Full Queues Separate add from offer

After two insertions into capacity 2, `bounded full offer C=false` indicates that C was not accepted. The sequence `[A, B]` is unchanged.

`bounded full add=IllegalStateException` also does not insert C. The queue is not left with an extra copy of C mixed in after the exception in this example.

When `bounded poll=A` frees a slot, the next `offer` attempt returns `true` and the result is `[B, C]`. C is added exactly once, on that later successful attempt.

### 10.4. Invalid Data Does Not Become false

`offer null=NullPointerException` and `add null=NullPointerException` occur on an empty `ArrayDeque`, so they cannot be explained by "out of space."

`after invalid inserts size=0` confirms that no member was added during those two failing calls.

## 11. Initial Capacity Is Not Necessarily Maximum Capacity

`new ArrayDeque<>(1)` does not create a queue that can only hold one element. `ArrayDeque` uses a backing array that can grow in capacity as needed.

The program inserts 1, 2, 3 and prints:

~~~text
growing offers=true/true/true
growing size=3
~~~

The constructor parameter here is an initial capacity hint sufficient to hold the requested number of elements, not a one-member limit. Therefore, using `ArrayDeque` to test "offer returns false when adding a second element" is a test built on a false assumption.

`ArrayDeque` sets no fixed capacity limit under its usage contract. That does not mean machine resources are infinite or that every call is guaranteed to succeed under all conditions. Do not interpret a resource failure as a full-queue condition that `Queue.offer` can universally represent with `false`. [Java 17: ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

`ArrayBlockingQueue` has a fixed capacity specified at creation time. That is why this lesson uses two different classes for two verification purposes: capacity growth and rejection due to reaching a limit.

When reading real code, determine whether a constructor parameter is an initial capacity or a maximum limit. Do not infer the meaning of the same number merely because both class names contain "Array."

## 12. Avoid Using null as a Queue Element

`poll` and `peek` use `null` to indicate that there is no head element. If the input data itself can be `null`, the return value is no longer enough to distinguish the two cases.

Many classes, including `ArrayDeque`, `PriorityQueue`, and `ArrayBlockingQueue`, forbid `null`. However, `LinkedList` allows `null` even when the object is viewed through the `Queue` type.

The program intentionally creates such a queue:

~~~text
[null, tail]
~~~

`peek` returns `null`, yet `size` remains 2 because nothing was removed. Afterward `poll` also returns `null`, but this time it removed the `null` member; the queue still has `tail` and `isEmpty` is `false`.

Therefore, the statement "if poll returns null, the Queue is always empty" only holds when the element contract excludes `null`. You must not deduce that for every implementation class without checking.

The `Queue` documentation advises against using `null` as an element even in classes that permit it. The `LinkedList` example in this lesson is a counterexample to illustrate the ambiguity, not a recommended way to represent work. [Java 17: LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

If an application needs a message meaning "no value" or "end," use an explicit message model suited to the data instead of overloading `null`, which the API uses as a special result. That model must be handled as part of the application contract.

## 13. remove() Differs from remove(Object)

The name `remove` has two important forms:

| Call | Meaning | Return Type |
| --- | --- | --- |
| `queue.remove()` | Retrieve and remove the head | Element of type `E` |
| `queue.remove(value)` | Find and remove one matching element by value | `boolean` |

The zero-argument form is `poll`'s partner in this lesson. The one-argument form is inherited from `Collection` and does not mean "remove the head."

For a FIFO `ArrayDeque` containing `[head, middle, tail]`:

~~~text
remove("middle") → true
queue            → [head, tail]

remove()        → head
queue           → [tail]

remove("missing") → false
~~~

In the value-lookup case, not finding the element is normally reported as `false` by contract; do not attribute the empty-queue exception of `remove()` to every call sharing the same name. [Java 17: Collection.remove(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#remove(java.lang.Object)).

With a variable typed as `Queue<Integer>`, `remove(1)` looks up an element with numeric value 1 via the `Object`-argument form, rather than removing at index 1 like some calls on `List`. `Queue` does not provide index-based removal.

Also, do not expect the two forms to have the same cost. For example, removing at the head of an `ArrayDeque` differs from searching for a value in the middle. When evaluating performance, identify the exact method signature, not just the name `remove`.

## 14. Same poll, Different Head in PriorityQueue Than FIFO

The program inserts `7, 2, 5, 2` into a `PriorityQueue` using the natural ordering of `Integer`. It does not print the whole `PriorityQueue` and assume that sequence is the removal order.

The results:

~~~text
priority size=4
priority peek=2
priority remove=2
priority poll=2
priority drain=[5, 7]
~~~

The head of the queue is the lowest-priority value according to the current rule, not the number 7 that arrived first. Both occurrences of 2 are kept; this is not a duplicate-eliminating `Set`.

`remove()` and `poll()` still perform the same head-removal purpose. They do not select two different priority policies. `peek` still only inspects the head.

For elements that have the same priority but are distinct objects, do not infer first-come-first-served ordering from equal priority keys unless the class guarantees it. If a requirement needs tie-breaking at that level, the model and comparator must reflect that requirement.

`PriorityQueue`'s iterator is not guaranteed to traverse in priority order. To verify the removal sequence in this lesson, the program uses actual head-removal calls. [Java 17: PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

## 15. Relationship to Deque: Add at Tail, Read/Remove at Head When Used as Queue

`Deque` extends `Queue` and allows operations at both ends. When using `Queue` methods on a `Deque`, they correspond operationally to:

| Queue | Equivalent Deque Method |
| --- | --- |
| `add(e)` | `addLast(e)` |
| `offer(e)` | `offerLast(e)` |
| `remove()` | `removeFirst()` |
| `poll()` | `pollFirst()` |
| `element()` | `getFirst()` |
| `peek()` | `peekFirst()` |

The table describes direction and effect. You still need to read the exact signatures: for example, `Queue.add` returns `boolean`, whereas `Deque.addLast` has a `void` return type.

The program keeps two variables pointing to the same `ArrayDeque`, one typed as `Deque` and one typed as `Queue`. Adding `first` via `Queue`'s `offer` and then adding `second` via `Deque`'s `offerLast` builds the same sequence of members.

`sameObject.peek()` and `deque.peekFirst()` both see `first`. After `remove` through the `Queue` variable takes `first`, `pollFirst` through the `Deque` variable takes `second`. There are not two independent data stores merely because the two variables have different types.

This relationship helps you read code when method names with `First`/`Last` suffixes appear alongside shorter `Queue` names. It does not mean you can freely swap adding at the head for adding at the tail; methods such as `addFirst` serve a different direction of operation. [Java 17: Deque, equivalence table with Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html).

## 16. These Methods Do Not Automatically Wait for Data or Space

The name `ArrayBlockingQueue` can lead beginners to think every call blocks and waits. You must read the exact method and signature.

In the program, `offer(e)` returns its result based on whether insertion is possible without waiting for space to appear; `poll()` does not wait for a new element to arrive. There is no timeout parameter in these signatures.

`BlockingQueue` adds waiting operations such as `put`, `take`, and timed variants. They are not among the six `Queue` signatures studied here. The existence of additional methods does not turn `add` or `element` into waiting operations. [Java 17: BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Also, do not infer thread safety from the `Queue` interface name alone. `ArrayDeque` in this lesson does not support arbitrary concurrent sharing and modification from multiple threads. `ArrayBlockingQueue` has its own coordination contract, yet a check-then-act sequence still needs to be read step by step.

For example, "check not full, then add" is two operations; another actor can insert in between. Similarly, "peek sees A, then poll" does not automatically reserve A for the caller that peeked.

When you only need to attempt an insertion, use the result of the `offer` call itself to know whether the operation just performed was accepted. When you need to remove, use the result of `poll` itself. Do not treat an earlier check as a permanent guarantee of the later state.

## 17. Which Pair to Choose for Your Code's Contract?

You do not need to memorize six names as six unrelated behaviors. Choose in two steps: determine the purpose, then determine how to represent failure.

| Situation | Choice to Consider |
| --- | --- |
| Inserting into a queue that may be full and needs to report non-acceptance | `offer`, then check the `boolean` |
| Failing to insert violates the code's assumption | `add` and an explicit exception contract |
| Taking work if currently available; being empty is normal | `poll`, then check for `null` when data forbids `null` |
| The code strictly requires a head element to remove | `remove()`; empty reports an error |
| Inspecting the head only; empty is an expected result | `peek` |
| Inspecting the head only; empty violates an assumption | `element` |

Do not ignore the result of `offer`. Do not call `poll` if you only need to inspect. Do not catch `NoSuchElementException` as a way to mask errors at every step without knowing whether the queue was supposed to have data.

For a pass that drains a null-forbidding queue, the method in the program:

~~~java
static <E> List<E> drainNonNullQueue(Queue<E> queue) {
    List<E> values = new ArrayList<>();
    E value;
    while ((value = queue.poll()) != null) {
        values.add(value);
    }
    return values;
}
~~~

both empties the queue and builds the result list. It is not a non-destructive read method and is unsuitable for queues with `null` elements.

If you only need to traverse for display, choose a read operation and check the iteration-order contract of the concrete class. If you need to keep all source data intact, do not pass it into a draining method only to realize afterward that "drain" means emptying the data out.

## 18. Common Mistakes

| Misconception | Accurate Reading |
| --- | --- |
| "Add inserts at the head, offer inserts at the tail" | Within the same `Queue` class, both share the insertion purpose; they differ in how they report no space |
| "Offer never throws an exception" | It can still report invalid data, such as a forbidden `null` |
| "No exception means offer succeeded" | You must check the returned `boolean` |
| "Offer true means the job has finished processing" | It only confirms that the insertion operation was accepted |
| "Poll only inspects the head" | `poll` returns the element and removes it |
| "Peek advances to the next element on each call" | If the data does not change, it keeps inspecting the same head |
| "Remove always throws when not found" | Distinguish zero-argument `remove()` from `remove(Object)` |
| "new ArrayDeque(2) can only hold two elements" | The argument is initial capacity, not a fixed limit |
| "Every Queue is FIFO" | Check the implementation class; `PriorityQueue` is a counterexample |
| "Poll returning null always proves the queue is empty" | Requires an element contract that forbids `null` |
| "Having 'Blocking' in the name means offer(e) waits for space" | Check the exact signature; separate waiting methods exist |
| "Peek then poll is one atomic action" | They are two calls; intervening changes can yield a different result |
| "Queue<Integer>.remove(1) removes at index 1" | Through the `Queue` type, that is the `Object` value-lookup form |

To find bugs quickly, write down the state before, the exact signature, the return value or exception, and the state after. Those four pieces of information are usually enough to separate an API-misunderstanding bug from an ordering-rule bug.

## 19. Guided Practice

### Exercise 1: Stepping Through Three Purposes

A FIFO queue starts as `[A, B]`. Call `peek`, `poll`, `element`, `remove` in order. What does each return, and what is the final state?

**Solution:** `peek` returns A and leaves the queue unchanged. `poll` returns A, leaving B. `element` returns B and keeps B. `remove` returns B, leaving the queue empty.

### Exercise 2: Operations When Empty

On an empty `ArrayDeque`, what do `poll` and `peek` return? What do zero-argument `remove` and `element` do?

**Solution:** `poll` and `peek` return `null`. `remove` and `element` throw `NoSuchElementException`. No element is added or synthesized as a substitute.

### Exercise 3: Two-Element Limit

An `ArrayBlockingQueue` of capacity 2 already holds X and Y. `offer` Z fails, then `add` Z is attempted. What are the two results and the contents?

**Solution:** `offer` returns `false`, `add` throws `IllegalStateException`. The queue remains `[X, Y]`. There is no Z waiting silently inside.

### Exercise 4: Retrying After Space Opens

Continuing from the previous exercise, `poll` removes X and then `offer` Z is called again. What happens?

**Solution:** Y and one empty slot remain. The new `offer` Z returns `true`, and the queue becomes `[Y, Z]`. The successful `offer` is a later call, not a delayed result of the rejected call.

### Exercise 5: Offering null

You switch from `add(null)` to `offer(null)` on an `ArrayDeque` to avoid an exception. Is that approach correct?

**Solution:** No. `ArrayDeque` forbids `null`, so both throw `NullPointerException`. The difference in full-queue behavior does not erase the input contract.

### Exercise 6: A peek Loop

Does a loop that checks `peek` is non-null and prints `peek` without removing automatically process elements one by one?

**Solution:** No. If the queue does not change, it keeps inspecting the same head. Use `poll` to remove elements one by one, or an iterator if only reading while preserving the data.

### Exercise 7: remove with an Argument

A FIFO queue is `[one, two, three]`. What does `remove("two")` return? What does `remove()` return afterward?

**Solution:** `remove` with an argument returns `true` and removes `two`, leaving `[one, three]`. Zero-argument `remove` returns the element `one` and removes the head, leaving `three`.

### Exercise 8: Initial Capacity

You create `new ArrayDeque<Integer>(1)` and `offer` three valid numbers. Can you conclude the second `offer` will return `false`?

**Solution:** No. `ArrayDeque` can grow its capacity and does not treat 1 as a maximum capacity. The program verified all three `offer` calls return `true` under normal conditions.

### Exercise 9: Priority Order

Insert `9, 4, 6` into a natural-order `PriorityQueue`. What do `peek`, `remove`, and `poll` return in sequence if no other operations intervene?

**Solution:** `peek` returns 4 and leaves the queue unchanged. `remove` returns 4, leaving 6 and 9. The next `poll` returns 6. It is not the case that 9, arriving first, is removed first.

### Exercise 10: null in LinkedList

A `Queue` backed by `LinkedList` contains `[null, tail]`. `poll` returns `null`. Can you stop processing and conclude all data has been consumed?

**Solution:** No. The call just removed the `null` member; `tail` is still there. This is why `null` should be avoided as `Queue` data and why loops polling until `null` require an explicit precondition.

### Exercise 11: Deque Relationship

On a `Deque` used as a `Queue`, does `offer` correspond to the head or the tail? Which side does zero-argument `remove` correspond to?

**Solution:** `offer` inserts at the tail, corresponding to `offerLast`. Zero-argument `remove` retrieves from the head, corresponding to `removeFirst`. `peek` inspects the head via `peekFirst`.

### Exercise 12: The Word "Blocking"

A `Queue` variable refers to a full `ArrayBlockingQueue`. If you call `offer(e)` with no timeout, does the call automatically wait until space is available?

**Solution:** It does not wait for space to appear; it reports that insertion failed by returning `false`. Waiting or timed operations belong to additional `BlockingQueue` signatures and must be chosen explicitly.

## 20. How to Remember This for Reading Real Code

First, classify the operation as **insert**, **remove**, or **inspect only**. Next, read how failure is reported: exception or `false`/`null`. Finally, check the implementation class for ordering, capacity limits, `null` policy, and multithreaded usage.

For each call, the return value describes that operation itself: `offer` returning `true` means inserted; `poll` returning non-null means removed when data forbids `null`; `peek` returning non-null only means the head was observed at the moment of the call. Keeping these meanings separate prevents most mistakes when using the three method pairs.
