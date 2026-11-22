# Special Values vs. Exceptions When Empty or Full

## 1. Empty and Full Are States; Calling Code Decides Whether They Are Abnormal

A queue receiving tasks may have nothing to process yet. A bounded buffer may have run out of room. Both are expected states in normal operation.

In another piece of code, however, the program may have established the condition "there must be an element to take." If that condition is false, continuing silently as if nothing happened hides a bug.

Java provides two ways to represent an operation that cannot be performed on `Queue` and `Deque`:

- Returning a **sentinel value**, typically `null` when no element is available or `false` when an element cannot be added due to capacity.
- Throwing an **exception**, such as `NoSuchElementException` when an element is required but the structure is empty, or `IllegalStateException` when adding to a full structure.

These two approaches do not change the underlying fact of whether "an element is currently present" or "space is available." They change how the outcome is communicated to the calling code.

This lesson focuses on choosing and handling that signal properly. We will verify both ends of a Deque, distinguish full/empty states from invalid-input errors, and handle the traps of null, zero, and auto-unboxing. All runnable examples use APIs available in Java 17.

You need to know variables, conditionals, loops, and method calls. You do not need to know how arrays or linked lists are organized internally to understand these contracts.

## 2. The Two Result Representations Differ in Control Flow

Consider a queue that does not store null elements and is currently empty.

With `poll()`:

~~~text
call poll
   ↓
receive null as a normal return value
   ↓
calling code checks and chooses a branch
~~~

With `remove()`:

~~~text
call remove
   ↓
throws NoSuchElementException
   ↓
normal execution flow leaves the call;
the exception is handled in an appropriate catch block or propagates outward
~~~

No element is returned normally from a remove call on an empty structure. An exception is not a value you compare with `== null`.

Conversely, null returned by poll does not automatically trigger a catch block. If subsequent code auto-unboxes null to a primitive type and causes an error, that is a separate event whose exact location must be identified.

A sentinel value requires the calling code to check it. An exception requires the code's contract to specify where it is handled or allow it to propagate. Neither approach by itself provides a business policy such as "retry," "drop the task," or "halt a stage."

## 3. Basic Map of Queue

`Queue<E>` describes a structure holding elements to be retrieved according to the implementation's policy. The head of the queue is the element that will be retrieved next; not every Queue uses the same ordering rule by default.

Three operations come in two forms:

| Operation | Exception-throwing form | Sentinel-value form |
| --- | --- | --- |
| Insert element | `add(e)` | `offer(e)` |
| Retrieve and remove head | `remove()` | `poll()` |
| Inspect head only | `element()` | `peek()` |

For valid data:

- When insertion succeeds, both add and offer return true.
- When full due to a capacity bound, add throws IllegalStateException, while offer returns false.
- When empty, remove and element throw NoSuchElementException.
- When empty, poll and peek return null.

Do not overlook "retrieve and remove" versus "inspect only." A successful poll removes a member from the queue; a successful peek leaves it in place. Changing a method name to change how emptiness is reported must not accidentally change the effect on the data. [Java 17: Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

The remove forms in the table all take **no arguments**. The `remove(Object)` method that searches by value is a different signature, not the empty-reporting counterpart in the remove/poll pair.

## 4. Deque Applies the Same Principle at Both Ends

`Deque` extends Queue to operate at both the front and the back. The `First`/`Last` suffix selects the end; the method-name group selects the operation and how failure is reported.

| End | Operation | Exception-throwing form | Sentinel-value form |
| --- | --- | --- | --- |
| Front | Insert | `addFirst(e)` | `offerFirst(e)` |
| Back | Insert | `addLast(e)` | `offerLast(e)` |
| Front | Retrieve and remove | `removeFirst()` | `pollFirst()` |
| Back | Retrieve and remove | `removeLast()` | `pollLast()` |
| Front | Inspect only | `getFirst()` | `peekFirst()` |
| Back | Inspect only | `getLast()` | `peekLast()` |

The offer methods return boolean. `addFirst` and `addLast` return void: normal completion indicates the insertion finished, whereas when full they signal failure with an exception. Do not assign the result of addLast to a boolean variable just because `Queue.add` has a boolean return type.

On an empty deque, the poll/peek methods at both ends return null. The remove/get methods at both ends throw NoSuchElementException. On a bounded deque that is already full, offer at either end may return false; add at that end throws IllegalStateException.

The front and back do not have two separate capacity pools. A deque with a capacity of two members cannot hold another element at the front just because the existing members were added at the back. [Java 17: Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html).

## 5. When Empty Is a Normal Outcome

Suppose each pass of a program takes the currently available tasks and then finishes. At the end of the pass, having no next element is expected.

Under a contract that does not store null, poll expresses this cleanly:

~~~java
String task = pending.pollFirst();
if (task == null) {
    System.out.println("Chưa có công việc.");
} else {
    System.out.println("Đã lấy: " + task);
}
~~~

This snippet assumes `pending` is a `Deque<String>` that contains no nulls. It reads the exact return value of the retrieval just performed.

Taking the no-task branch does not mean the data structure is broken. It may simply mean this pass received nothing. There is no need to turn every empty outcome into an application exception if the caller is allowed to encounter an empty queue.

Similarly, peek is appropriate when you only want to check what is at the head without removing it. However, peek does not advance processing progress. If you need to drain everything, inspecting repeatedly will not empty the structure.

The key point is that **normal versus abnormal is determined by the usage contract**, not by the word "empty" itself. The same ArrayDeque can be used in two places with two different expectations.

## 6. When Empty Proves a Broken Assumption

An algorithm may require retrieving a specific element that an earlier step already established must exist. When no intervening code modifies the structure, being empty at that point can indicate a bug in program flow.

Using removeFirst expresses the assumption that an element must be present:

~~~java
String required = pending.removeFirst();
System.out.println(required);
~~~

This snippet assumes pending belongs to a part of an algorithm whose contract requires it to be non-empty. If that condition is not met, NoSuchElementException appears immediately at the retrieval call.

If you replace it with pollFirst and ignore null, the bug can be pushed further away: a string operation might later cause a NullPointerException, or a subsequent branch might silently skip a step that should have run. A signal close to the cause usually makes it easier to re-examine the assumption.

This is not a rule to "always use exceptions to check for emptiness." If running out of tasks is expected to happen regularly, using poll with an explicit branch usually expresses intent more directly. Conversely, if emptiness violates an assumption, a clear error should not be turned into a normal result just to avoid seeing an exception.

NoSuchElementException is a runtime exception used when a requested element does not exist. You should read the exact method that threw it rather than treating it as a generic signal that "everything failed." [Java 17: NoSuchElementException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NoSuchElementException.html).

## 7. When Full Is a Branch to Handle, Not a Silent Overwrite

A fixed-capacity buffer usually needs a policy when no space remains—for example, reporting an unaccepted result to the sender or retrying in another phase.

With a `LinkedBlockingDeque` created with capacity 2 and containing `[older, newer]`:

~~~text
offerFirst(urgent) → false
offerLast(later)   → false
~~~

Neither new element is inserted. `urgent` does not silently push `newer` out to take its place. Nor is a rejected insertion queued up internally waiting for later.

If you call addFirst or addLast in the same full state, they throw IllegalStateException. The example in this lesson compares the contents before and after to confirm that both reporting styles preserve existing members across those individual calls.

After pollLast removes `newer`, a new offerFirst call can accept `urgent`:

~~~text
[older]
   ↓ offerFirst(urgent) succeeds
[urgent, older]
~~~

The true return value belongs to the new attempt after space became available. The earlier false does not retroactively turn into true when the state later changes.

LinkedBlockingDeque can be constructed with a specific capacity limit. This lesson chooses capacity 2 to make the full state easy to observe while using only a single thread. [Java 17: LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

## 8. Do Not Ignore false and Treat the Work as Accepted

When you choose the sentinel-value form, you also take responsibility for handling the result. Calling offerLast and discarding the boolean loses critical information at the exact point where an element can be rejected.

An illustrative method with a simple contract:

~~~java
static boolean tryAccept(Deque<String> buffer, String task) {
    return buffer.offerLast(task);
}
~~~

This is a helper method placed in a class, assuming task and buffer satisfy the data policy. The caller still needs to use the return value; adding a wrapper that continues to ignore the boolean solves nothing.

If it returns false, you can report that it was not accepted or hold the task on the caller side to apply the defined policy. Do not claim the item was queued successfully just because execution did not enter a catch block.

If it returns true, the insertion operation was accepted. That does not prove the element has finished processing. The queue only holds data; processing logic lives elsewhere.

Likewise, do not retry infinitely in a tight offer loop with no policy. Using a sentinel value does not by itself provide backoff, waiting for space, or a retry limit.

## 9. Input Errors Differ from Being Out of Space

The offer form is not a "never throws" variant. If a class forbids null, `offerFirst(null)` or `offerLast(null)` can throw NullPointerException even when the structure is empty and has plenty of room.

In ArrayDeque, null is not a valid element. That error is about the **input**, not about the member count reaching a limit.

Similarly, a Queue that requires comparable elements can fail when given an incompatible type. Switching from add to offer does not change the implementation's element-acceptance rules.

Therefore, classify outcomes by their actual cause:

| Signal | First question to check |
| --- | --- |
| offer returns false | The call did not accept the element; what are the capacity state and insertion policy? |
| NoSuchElementException from remove/get | Did the code require an element when the structure was empty? |
| IllegalStateException from add when full | Was a capacity limit reached? |
| NullPointerException when adding null | Does the class forbid null elements? |
| NullPointerException after poll | Did calling code use or auto-unbox a null result? |

An exception name alone does not describe the whole cause. The call site and the method's contract tell you which category it belongs to.

Do not catch an overly broad exception and turn every cause into "full" or "empty." Doing so makes data errors look like normal states and makes fixing the true cause harder.

## 10. Complete Program Using Java 17

Save as `QueueFailureSignalsDemo.java`. The program verifies:

- Four poll/peek calls and four remove/get calls on an empty deque.
- Insertion at both ends of a bounded deque that is full.
- Making room and retrying.
- A valid 0 compared with a null result.
- An auto-unboxing error and a null-insertion error.
- A class that permits null to test the boundaries of these conclusions.
- A violated non-empty assumption.

Expected exceptions are caught tightly around each call so that subsequent example groups still run. The code does not wrap the entire program in a single catch block.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.concurrent.LinkedBlockingDeque;

public class QueueFailureSignalsDemo {
    // Precondition: no nulls stored and no other code modifies the deque during this pass.
    static List<String> consumeAvailable(Deque<String> pending) {
        List<String> consumed = new ArrayList<>();
        String task;
        while ((task = pending.pollFirst()) != null) {
            consumed.add(task);
        }
        return consumed;
    }

    public static void main(String[] args) {
        Deque<String> empty = new ArrayDeque<>();
        System.out.println("empty pollFirst=" + empty.pollFirst());
        System.out.println("empty pollLast=" + empty.pollLast());
        System.out.println("empty peekFirst=" + empty.peekFirst());
        System.out.println("empty peekLast=" + empty.peekLast());
        try {
            empty.removeFirst();
        } catch (NoSuchElementException exception) {
            System.out.println("empty removeFirst=" + exception.getClass().getSimpleName());
        }
        try {
            empty.removeLast();
        } catch (NoSuchElementException exception) {
            System.out.println("empty removeLast=" + exception.getClass().getSimpleName());
        }
        try {
            empty.getFirst();
        } catch (NoSuchElementException exception) {
            System.out.println("empty getFirst=" + exception.getClass().getSimpleName());
        }
        try {
            empty.getLast();
        } catch (NoSuchElementException exception) {
            System.out.println("empty getLast=" + exception.getClass().getSimpleName());
        }
        System.out.println("empty unchanged=" + empty.isEmpty());

        Deque<String> limited = new LinkedBlockingDeque<>(2);
        limited.addLast("older");
        limited.addLast("newer");
        List<String> before = new ArrayList<>(limited);
        System.out.println("full initial=" + limited);
        System.out.println("full offerFirst=" + limited.offerFirst("urgent"));
        System.out.println("full offerLast=" + limited.offerLast("later"));
        System.out.println("after false unchanged=" + before.equals(new ArrayList<>(limited)));
        try {
            limited.addFirst("urgent");
        } catch (IllegalStateException exception) {
            System.out.println("full addFirst=" + exception.getClass().getSimpleName());
        }
        try {
            limited.addLast("later");
        } catch (IllegalStateException exception) {
            System.out.println("full addLast=" + exception.getClass().getSimpleName());
        }
        System.out.println("after exceptions unchanged="
                + before.equals(new ArrayList<>(limited)));
        System.out.println("full peekFirst/peekLast="
                + limited.peekFirst() + "/" + limited.peekLast());
        System.out.println("full size after peeks=" + limited.size());
        System.out.println("make room pollLast=" + limited.pollLast());
        System.out.println("retry offerFirst=" + limited.offerFirst("urgent"));
        System.out.println("after retry=" + limited);
        System.out.println("consumed=" + consumeAvailable(limited));
        System.out.println("empty after consume=" + limited.isEmpty());

        Deque<Integer> numbers = new ArrayDeque<>();
        numbers.offerLast(0);
        Integer zero = numbers.pollFirst();
        System.out.println("zero value=" + zero);
        System.out.println("zero is present=" + (zero != null));
        Integer absent = numbers.pollFirst();
        System.out.println("absent value=" + absent);
        try {
            int unsafe = numbers.pollFirst();
            System.out.println("unboxed value=" + unsafe);
        } catch (NullPointerException exception) {
            System.out.println("unboxing empty result=" + exception.getClass().getSimpleName());
        }
        try {
            numbers.offerLast(null);
        } catch (NullPointerException exception) {
            System.out.println("invalid null input=" + exception.getClass().getSimpleName());
        }
        System.out.println("numbers size=" + numbers.size());

        Deque<String> nullable = new LinkedList<>();
        nullable.addLast(null);
        nullable.addLast("tail");
        System.out.println("nullable getFirst=" + nullable.getFirst());
        System.out.println("nullable size after get=" + nullable.size());
        System.out.println("nullable removeFirst=" + nullable.removeFirst());
        System.out.println("nullable size after remove=" + nullable.size());
        System.out.println("nullable remaining=" + nullable);

        Deque<String> required = new ArrayDeque<>();
        required.addLast("ready");
        System.out.println("required first removal=" + required.removeFirst());
        try {
            required.removeFirst();
        } catch (NoSuchElementException exception) {
            System.out.println("broken nonempty assumption="
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 QueueFailureSignalsDemo.java
java QueueFailureSignalsDemo
~~~

Use JDK 17 or newer. `--release 17` checks the code and API against Java 17. The filename matches the public class.

Expected output:

~~~text
empty pollFirst=null
empty pollLast=null
empty peekFirst=null
empty peekLast=null
empty removeFirst=NoSuchElementException
empty removeLast=NoSuchElementException
empty getFirst=NoSuchElementException
empty getLast=NoSuchElementException
empty unchanged=true
full initial=[older, newer]
full offerFirst=false
full offerLast=false
after false unchanged=true
full addFirst=IllegalStateException
full addLast=IllegalStateException
after exceptions unchanged=true
full peekFirst/peekLast=older/newer
full size after peeks=2
make room pollLast=newer
retry offerFirst=true
after retry=[urgent, older]
consumed=[urgent, older]
empty after consume=true
zero value=0
zero is present=true
absent value=null
unboxing empty result=NullPointerException
invalid null input=NullPointerException
numbers size=0
nullable getFirst=null
nullable size after get=2
nullable removeFirst=null
nullable size after remove=1
nullable remaining=[tail]
required first removal=ready
broken nonempty assumption=NoSuchElementException
~~~

## 11. Reading the Output by Before-and-After State

### 11.1. Empty Deque Without Corruption

The four lines `empty pollFirst`, `pollLast`, `peekFirst`, and `peekLast` all return null. They do not synthesize a default element.

The four remove/get forms report NoSuchElementException. After all those calls, `empty unchanged=true` confirms the deque is still empty.

The difference lies in how "no element" is communicated to the calling code, not in one side repairing the structure while the other breaks it.

### 11.2. Rejecting When Full Does Not Delete Existing Members

Two offer calls return false and two add calls throw IllegalStateException. The program snapshots the prior member sequence with an ArrayList and compares after each group:

~~~text
after false unchanged=true
after exceptions unchanged=true
~~~

This checks both contents and order in a single-threaded example, not just size. Having the same size is not enough to prove the members did not change, so a snapshot makes the comparison clearer.

This conclusion applies to the individual verified calls. It does not mean a sequence of multiple different operations is a transaction that rolls back if the last step throws an exception.

### 11.3. Inspecting Does Not Free Capacity

`full peekFirst/peekLast=older/newer` and `full size after peeks=2` show that inspecting both ends removes nothing.

A mutating operation such as pollLast is required to make room in the example. After removing `newer`, offerFirst accepts `urgent` and the order becomes `[urgent, older]`.

### 11.4. Running Out of Work Is a Valid Stopping Point

`consumed=[urgent, older]` shows that `consumeAvailable` retrieved both members. The next pollFirst call returns null, the loop terminates, and `empty after consume=true`.

This method has the preconditions that no nulls are stored and no other code modifies the deque during the demonstrated pass. The result must not be generalized into a guarantee for every structure or every multi-threaded usage.

## 12. Zero Is Not a Standard Marker for an Empty Queue

`Queue<Integer>` or `Deque<Integer>` stores Integer objects. An element with value 0 is still a real element.

In the program:

~~~text
zero value=0
zero is present=true
absent value=null
~~~

The first pollFirst retrieves 0. Only the next call finds no element and returns null. If code chooses `value == 0` to represent emptiness, it loses the ability to represent a valid data value.

Do not substitute an empty string, a negative number, or another arbitrary value for null unless the data domain explicitly reserves that value by contract. The API already defines the empty-reporting result; changing its meaning without controlling the input domain creates ambiguity.

How to check safely before unboxing in the numeric example:

~~~java
Integer next = numbers.pollFirst();
if (next != null) {
    int value = next;
    System.out.println(value);
}
~~~

This snippet assumes numbers is a `Deque<Integer>` that forbids null. The null check occurs before converting to int.

## 13. Auto-Unboxing Can Turn a Normal Signal into an Error

The line:

~~~java
int value = numbers.pollFirst();
~~~

looks like reading a number. In reality, pollFirst returns an Integer, and Java converts that object to int via auto-unboxing.

If the result is null, that conversion throws NullPointerException. An empty state that the API originally represented with a normal return value becomes an error in the calling code.

The program prints `unboxing empty result=NullPointerException` to make this path explicit. It also prints another NullPointerException when attempting to add null to an ArrayDeque. Both errors share the same exception name, but they arise from two different causes and at two different points.

The language specification defines that unboxing a null reference throws NullPointerException. Therefore, you cannot avoid the error merely by using Integer as the generic element type while still assigning the result directly into an int. [Java Language Specification 17: unboxing](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8).

For other reference-type elements, calling a method directly on the result of poll runs into the same issue if you do not check for null. You must decide how to handle a missing element before using the data as if it were guaranteed to exist.

## 14. Exception-Throwing Methods Do Not Always Guarantee a Non-Null Return

In most examples in this lesson, ArrayDeque and LinkedBlockingDeque forbid null. That keeps the empty-reporting null from being confused with data.

However, LinkedList permits null. The program deliberately constructs the deque:

~~~text
[null, tail]
~~~

and gets:

~~~text
nullable getFirst=null
nullable size after get=2
nullable removeFirst=null
nullable size after remove=1
nullable remaining=[tail]
~~~

`getFirst` completes normally and returns a null member, because the structure is **not empty**. `removeFirst` also completes normally, removing that null member.

Thus, "throws when empty" is different from "every normal completion returns a non-null value" if the implementation allows null as data. The exception is tied to the absence of an element, not to every possible null outcome.

With poll/peek on a class that permits null, null can be either an element's value or the signal that no element exists. Merely wrapping the result in another type or renaming variables does not recover information that is already ambiguous.

The Queue/Deque documentation advises against using null as an element. The LinkedList example here tests the boundary of the conclusion, not a recommended way to represent work in a queue. [Java 17: LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

## 15. Keep Exception-Handling Scope Tight to the Contract

If you choose a method that can throw on empty, know exactly which region is allowed to be interpreted as "no element."

An overly broad try block may enclose element retrieval, data parsing, and processing. If the processing step also throws NoSuchElementException from a different data source, catching it and concluding "the deque is empty" misinterprets the cause.

In the demo code, each try block focuses on the single call being tested. That helps tie each signal to its state. In application code, you may let the error propagate if it represents a broken assumption that needs fixing rather than catching it to continue.

If running out of data is an expected situation, poll and an explicit branch usually make the scope of an absent result easier to read. The following method is an excerpt from the full program:

~~~java
static List<String> consumeAvailable(Deque<String> pending) {
    List<String> consumed = new ArrayList<>();
    String task;
    while ((task = pending.pollFirst()) != null) {
        consumed.add(task);
    }
    return consumed;
}
~~~

The method returns a list of retrieved elements and drains the passed-in deque in the single-threaded example. It is not an inspection or a copy that leaves the source data intact.

If processing an element after poll fails, the deque does not automatically put the element back. Recovery or error marking is a separate application contract, not something implied by how poll reports emptiness.

## 16. Do Not Fake a Full State Without a Fixed Capacity

Having a sentinel branch on offer does not mean every class reaches a full state in the same way.

ArrayDeque can grow its capacity as needed. The argument in `new ArrayDeque<>(2)` is not a hard limit of two members. You cannot use adding a third element to prove that offer must return false.

LinkedBlockingDeque in this lesson is created with capacity 2 so that the full state is well defined. Do not infer capacity limits from the words "linked" or "array"; read the constructor and class contracts.

Having no fixed API capacity limit also does not mean machine memory is infinite. Resource exhaustion errors are not a universal capacity signal that offer is required to convert into false. [Java 17: ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

When writing tests, an empty state requires a structure with zero members, whereas a full state requires an implementation with a real bound and filling all of those slots. Choosing small data that meets the exact condition matters more than looping many times over an unbounded class.

## 17. Sentinel Values Are Not a Waiting Mechanism

Both the sentinel-value style and the exception-throwing style covered here describe immediate operations under specific signatures.

The name LinkedBlockingDeque does not make `offerFirst(e)` wait until space opens up. `pollFirst()` does not wait for a new element to arrive. In the program, each call reports immediately whether insertion or retrieval succeeded without waiting for capacity or data to change.

BlockingDeque provides additional methods such as put/take and timed variants. If the requirement is to wait, or wait up to a timeout, you must choose the right signature and understand its contract. Do not assume that switching from add to offer provides a waiting policy. [Java 17: BlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

Also do not treat "check then act" as an atomic action:

~~~text
isEmpty returns false
   ↓
another actor may remove the element
   ↓
removeFirst can still encounter empty
~~~

Similarly, seeing an empty slot earlier does not guarantee a subsequent add will still have room in an environment with interleaved operations.

If having no element yet is normal, handle the result of the poll call itself. If waiting is required, choose a waiting API. If an entire sequence of operations must be protected, design appropriate coordination. ArrayDeque by itself does not provide thread-safe sharing and mutation.

The examples in this lesson run on a single thread so state outcomes are clear; they are not concurrency tests.

## 18. Misconceptions to Catch Early

| Misconception | Correction |
| --- | --- |
| "Empty is always an error" | Check the contract: it may be the normal state of a work-draining pass |
| "If you don't want errors, just change every remove to poll" | That can hide a non-empty assumption and push the bug elsewhere |
| "Offer never throws exceptions" | Invalid input can still fail |
| "No catch block means insertion succeeded" | You must read and handle offer's boolean |
| "False means the element will be added automatically later" | The call rejected the element; retrying is a new operation |
| "Peek makes room because it looked at the element" | Peek/get only read; they do not remove |
| "Null unboxes to a default 0" | Unboxing null throws NullPointerException |
| "0 means the queue is empty" | 0 can be a valid Integer element |
| "Normal completion of get/remove always returns non-null" | A class that permits null can return an actual null member |
| "Replacing null with an empty string removes all ambiguity" | An arbitrary value may belong to the data domain without a dedicated contract |
| "AddFirst returns boolean like Queue.add" | `addFirst`/`addLast` return void; `offerFirst`/`offerLast` return boolean |
| "A Deque has separate space at each end" | The capacity limit applies to the total member count |
| "Checking non-empty beforehand makes remove guaranteed safe" | You must consider whether intervening modifications can occur |
| "One failed call rolls back the preceding sequence" | Completed operations do not automatically form a transaction |

When investigating an error, preserve four pieces of information: which method was called, the prior state, the actual signal received, and the resulting state. Do not just record "operation failed."

## 19. Guided Practice

### Exercise 1: Choosing a Signal for a Drain-Available Pass

A processing pass is allowed to end when no next task is available. `pollFirst` returns null on a deque that forbids null. Should you convert it into NoSuchElementException?

**Solution:** No, if emptiness is part of this pass's normal contract. Check for null and finish or take the appropriate branch. An exception adds no information in an expected case.

### Exercise 2: Required-Element Assumption

An algorithm step must retrieve an element produced by the previous step, with no intervening operations. `removeFirst` throws NoSuchElementException. What should you examine first?

**Solution:** Check the assumption and the element-production/consumption flow. Do not immediately switch to poll and ignore null just to make the error disappear; emptiness may be a sign that the algorithm is wrong.

### Exercise 3: Full at Both Ends

A deque of capacity 2 already holds `[A, B]`. What do `offerFirst(C)` and `offerLast(D)` return respectively?

**Solution:** Both return false if no intervening operation frees space. Capacity applies to the whole deque, not two slots per end.

### Exercise 4: Same Full State Using add

Still with `[A, B]` at capacity 2, how do `addFirst(C)` and `addLast(D)` report the state?

**Solution:** Each individual call throws IllegalStateException because there is no room. Under the single-threaded conditions of the example, the existing members remain unchanged after each rejection.

### Exercise 5: Does Reading Free Space?

The deque is full, and you call `peekFirst` and `getLast` successfully. Is a subsequent `offer` guaranteed to return true?

**Solution:** No. Both calls only inspect without removing members. If the structure is still full, offer can still return false.

### Exercise 6: Zero and Absence

A `Deque<Integer>` that forbids null contains a 0. `pollFirst` returns 0, and the next call returns null. Can 0 be used as the termination condition?

**Solution:** No, if 0 belongs to the data domain. You must keep the `Integer` to check for null first, and only unbox to `int` when an element is present.

### Exercise 7: Auto-Unboxing Null

An `int` variable directly receives `pollFirst()` from an empty deque. Does it receive 0?

**Solution:** No. The Integer result is null, and auto-unboxing throws NullPointerException. No default int value is returned instead.

### Exercise 8: Same Error Name, Different Causes

One NullPointerException occurs on `offerLast(null)`, and another occurs at `int n = deque.pollFirst()`. Do both mean the deque is full?

**Solution:** No. The first may be a violation of a null-forbidding policy. The second is unboxing a null result caused by the absence of an element. You must examine the exact call site and contract.

### Exercise 9: Real Null in LinkedList

A deque backed by LinkedList contains `[null, X]`. Must `getFirst` and `removeFirst` throw an error?

**Solution:** No, because the structure is not empty and LinkedList permits null. `getFirst` returns null without removing it; `removeFirst` returns null and removes that member, leaving `X`.

### Exercise 10: Out of Space but Still Reporting Success

A method calls `offerLast` and always returns true to the sender. When the deque is full, what is wrong?

**Solution:** The method ignores false and reports acceptance of an element that was never inserted. It must propagate or handle the actual result, then apply the defined rejection or retry policy.

### Exercise 11: Constructor Capacity Argument

You construct an ArrayDeque with the number 2 and expect the third member to cause IllegalStateException. Which assumption needs correcting?

**Solution:** That number is not a fixed maximum capacity for ArrayDeque. To verify fullness due to a bound, use a genuinely bounded class such as LinkedBlockingDeque constructed with capacity 2 as in the lesson.

### Exercise 12: Checking Before Retrieving

In an environment where other actors also consume data, `isEmpty` just returned false. Can you ignore the possibility that `removeFirst` encounters an empty deque?

**Solution:** No. State can change between the two calls. Handle the result of the actual retrieval operation, use a waiting API if needed, or protect the sequence under an appropriate coordination contract.

## 20. Final Question Before Choosing a Method

Before each read or insertion point, ask: **is the empty/full state here an allowed outcome or a sign that an assumption has been broken?**

If it is an allowed outcome, choose the sentinel-value form and handle false/null completely. If it violates an assumption, keep a clear failure signal and decide where it is handled or propagated.

Then check the data policy separately—especially null handling, return type, and removal side effects. The way failure is reported is no substitute for understanding the class you are using, and a normal return value is only useful when calling code preserves its meaning.
