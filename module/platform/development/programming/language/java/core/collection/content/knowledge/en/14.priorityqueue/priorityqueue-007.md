# Risks of Modifying the Priority of an Object Already in the Queue

## 1. A setter can change data without changing the position in the heap

Suppose a PriorityQueue selects the job with the smallest priority number first. It currently holds A:10, B:20, C:30, D:40, and E:50. Then, the caller modifies the same object D to D:1.

Based on the current values, D should be prioritized before A. However, PriorityQueue does not automatically listen to every setter on its elements to move D to the front. The object remains in the position chosen when it still had priority 40.

There are three layers that must be kept distinct:

```text
reference stored by the queue
        |
        v
object and its current data
        |
        v
ordering relation read by the comparator

position in the heap organized at an earlier point in time
```

Modifying an object's field changes the data that the comparator may read, but it does not automatically perform an offer, remove, or heap-update operation.

The typical consequence is selecting the wrong job according to current priorities, while the size remains accurate and the object still exists in the queue.

This article explains that risk, how to recognize it, and controlled ways to perform updates. Related API contracts are referenced against [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

## 2. The heap invariant must hold before each subsequent operation

For a min-heap ordered by ascending priority number, a fundamental invariant is:

```text
parent's priority <= each child's priority
```

A valid illustrative structure:

```text
             A:10
            /    \
         B:20    C:30
         /  \
      D:40  E:50
```

Modifying D:40 to D:1 without updating the structure:

```text
             A:10
            /    \
         B:20    C:30
         /  \
       D:1  E:50
```

The relation that B:20 precedes D:1 is no longer valid. Because D has not been moved up, the root A:10 is also no longer the smallest element according to current values.

This is an illustrative diagram matching the upcoming experiment, not a contract on internal layout across all JDKs.

### 2.1. Changes in either direction can cause errors

If the priority number of a lower element is decreased, it may need to move up. If the priority number of the head element is increased, it may need to move down.

For example, if the root A:10 is changed to A:100, peek may still return it before B:20, because mutating the field does not automatically trigger a sift-down.

It is best to state the convention explicitly: in this article, **smaller numbers are retrieved first**. The phrase "increase priority" in business logic sometimes means decreasing the number; avoid ambiguous wording when explaining changes.

### 2.2. A single mutation might happen not to break the relation yet

Not every value change immediately produces wrong output in every layout. An element might still remain within the valid range between its parent and children after a small change.

That does not constitute an auto-update mechanism. Just because a test does not yet show a failure does not mean arbitrarily mutating fields read by the comparator is safe.

A controllable rule is to keep the data determining order stable while the element is in the queue, and to perform changes through an explicit update flow.

### 2.3. Poll is not responsible for re-checking all data

Poll relies on the assumption that the heap is valid: it removes the root, moves the last element into the gap, and repairs a path downward.

It does not scan every element to re-find the minimum based on data modified externally. An invariant broken on another path can remain broken after a poll.

Nor should an arbitrary offer be used as a "full refresh" operation. Offer repairs the path of the new element; it does not scan every object that has been modified by a setter.

## 3. Program 1: contains is still true, but the priority head is wrong

Save the file `MutablePriorityFailureDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class MutablePriorityFailureDemo {
    static final class Task {
        private final String id;
        private int priority;

        Task(String id, int priority) {
            this.id = id;
            this.priority = priority;
        }

        int priority() {
            return priority;
        }

        void changePriority(int newPriority) {
            priority = newPriority;
        }

        @Override
        public String toString() {
            return id + ":" + priority;
        }
    }

    public static void main(String[] args) {
        Comparator<Task> order = Comparator.comparingInt(Task::priority);
        Task a = new Task("A", 10);
        Task b = new Task("B", 20);
        Task c = new Task("C", 30);
        Task d = new Task("D", 40);
        Task e = new Task("E", 50);
        List<Task> input = List.of(a, b, c, d, e);
        PriorityQueue<Task> tasks = new PriorityQueue<>(order);
        tasks.addAll(input);

        System.out.println("head before change = " + tasks.peek());
        d.changePriority(1);

        System.out.println("size after change = " + tasks.size());
        System.out.println("contains changed reference = " + tasks.contains(d));
        System.out.println("minimum by fresh scan = "
                + input.stream().min(order).orElseThrow());
        System.out.println("head after change = " + tasks.peek());
        System.out.println("first poll after change = " + tasks.poll());
        System.out.println("head after one poll = " + tasks.peek());

        List<String> output = new ArrayList<>();
        Task next;
        while ((next = tasks.poll()) != null) {
            output.add(next.toString());
        }
        System.out.println("remaining poll order = " + output);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 MutablePriorityFailureDemo.java
java MutablePriorityFailureDemo
```

Verification run output:

```text
head before change = A:10
size after change = 5
contains changed reference = true
minimum by fresh scan = D:1
head after change = A:10
first poll after change = A:10
head after one poll = B:20
remaining poll order = [B:20, D:1, C:30, E:50]
```

This experiment intentionally breaks the heap invariant. The code uses language features and APIs available in Java 17 and later, compiled with `--release 17` and verified on Azul OpenJDK 24.0.2. The mechanism is cross-checked against the OpenJDK 17 source code.

The element selection lines after the change are observations of the tested implementation, not a contract that every JDK must fail in the exact same sequence.

### 3.1. Size and contains do not check heap order

Size is still 5. Contains with the exact reference d still returns true. This is consistent with the queue still holding that object.

However, these are two different questions:

```text
Is the object still in the queue?
Is the queue selecting the highest-priority object?
```

A fresh scan using current data finds D:1. Peek on the stale heap still returns A:10. Membership does not prove that the priority index is still valid.

### 3.2. A single poll does not fix the whole problem

After polling A:10, the next head is still B:20 even though D:1 is waiting. The remaining sequence is B:20, D:1, C:30, E:50, showing that you cannot rely on a single poll to heal the entire heap.

In the illustrative model, after the first poll, the relation may still look like:

```text
        B:20
       /    \
     D:1    C:30
     /
   E:50
```

The local repair path did its job under the old assumption, yet the head is still not smaller than every element.

### 3.3. No exception does not mean correct priority

The setter neither adds nor removes an item from the queue. There is no general requirement forcing it to increment a structural modification counter or throw ConcurrentModificationException.

The program can run to completion and return all objects, yet the processing order is wrong. This is a violation of the data-ordering invariant, not necessarily a missing-element error or a memory-access exception.

## 4. Why doesn't the queue snapshot or track priority automatically?

### 4.1. The queue holds references to elements

If you insert a mutable object into a PriorityQueue, the queue does not by default clone the entire object or store an independent immutable copy of its priority.

Another reference can still invoke a setter. When the comparator is called again, it sees the new data; however, the positional relationships established earlier may no longer match the new data.

Therefore, the fact that the comparator reads the new number does not mean the structure has been repositioned properly.

### 4.2. A comparator that is valid at each instant is not enough

A comparator using Integer.compare on a priority field may be sound with respect to sign and transitivity at any given data state.

The lifecycle issue is that the comparison relationship between elements already inside the heap changed without going through a structure-maintaining operation.

Both layers must be checked:

1. Does the comparator express a valid ordering relation?
2. Is the data that relation depends on kept stable between queue updates?

Fixing a comparison formula does not by itself resolve a setter mutating data outside the managed flow.

### 4.3. final and record only protect what they actually hold

`final PriorityQueue<Task>` only prevents reassigning that variable to a different queue. It does not make Task elements immutable.

`final Comparator<Task>` only fixes the comparator reference. If the comparator reads a mutable configuration Map, the ordering result can still change.

Records are also not automatically deeply immutable. The [Java 17 Record documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html) describes records as shallowly immutable: a reference component can point to a mutable object.

For example, a record containing a mutable PriorityState can still change comparison results when PriorityState changes. A record containing only integers and immutable Strings, as in the safe example below, is much easier to keep stable.

### 4.4. Indirect changes must also be audited

Paths that change priority can include:

- A direct setter on the priority field.
- A nested object read by the comparator.
- An external Map used by the comparator to look up the current level.
- A configuration flag that reverses or alters the comparison criteria.
- A scoring rule based on external state that swaps the relative order of two jobs.

What matters is whether the ordering relation changes. Not all external data causes bugs, but any source capable of altering the ordering relation requires an appropriate mechanism to update the structure.

## 5. contains, equals, and comparator serve different roles

PriorityQueue uses the comparator or Comparable to organize priority. However, contains and remove(Object) search using equals.

In the first example, Task does not override equals, so it uses default object identity; contains(d) succeeds for the exact reference. Another class implementing equals by id will have a different matching behavior.

These roles should be clearly distinguished:

| Operation | Relation used |
|---|---|
| Selecting priority head, sift-up/sift-down | Comparator or Comparable |
| contains(x), remove(x) by object | Equals |
| Comparing the same object via two references | May use == when the algorithm specifically needs reference identity |

Do not explain PriorityQueue bugs using HashSet bucket rules. PriorityQueue does not use hashCode to determine priority position or to perform the linear search in remove(Object).

### 5.1. Remove after mutation may still find the element

Because remove(Object) searches by equals, changing priority does not necessarily make it unable to find the item. If equals or the exact reference still matches, the call can return true.

However, finding it to remove does not prove that the queue returned the right priority earlier. If an incorrect poll has already occurred, removing later does not undo past processing decisions.

A more controlled approach is to remove while the old data is still stable, confirm removal succeeded, and then mutate or create the new value and re-add it.

### 5.2. Remove only removes a single equal occurrence

PriorityQueue allows duplicate elements. If the same object is offered multiple times, removing it once does not guarantee no references to it remain in the queue.

If there are multiple distinct objects considered equal by equals, remove(target) is also not by default an API that removes strictly by target's reference identity.

Before using remove to update a job, you need a clear identity and multiplicity policy. Do not assume the queue automatically guarantees one record per id.

### 5.3. Account for the cost accurately

Remove(Object) may need to scan through n elements, making it O(n) in general, plus maintaining the heap around the removal spot. The subsequent offer has an O(log n) heap cost.

Therefore, updating via remove followed by offer does not automatically have an O(log n) bound for the entire operation. If priority updates are very frequent at large scale, evaluate a different structure or update model.

## 6. Explicit update: remove first, mutate or replace, then add

A basic flow under controlled conditions:

```text
identify the exact waiting job
    -> prepare and validate the new data
    -> remove the old job while its info is still stable
    -> confirm removal succeeded
    -> mutate or create the new value
    -> offer the new value
```

### 6.1. If you still use mutable objects

Illustrative snippet:

```java
// Snippet in a single-threaded flow, with a unique managed element.
if (!queue.remove(task)) {
    throw new IllegalStateException("Task is not queued");
}
task.changePriority(newPriority);
queue.offer(task);
```

This is not a universal update function for every system. It assumes:

- The task to update is identified accurately.
- No other occurrence of the same mutable key remains in the queue.
- No other queue is concurrently organized by the same mutated object.
- No updates interleave between steps.
- The new data and comparator satisfy the required contract.

If an object is also present in multiple priority structures, removing it from one and mutating it can still corrupt the others.

### 6.2. It is often easier to control by creating a new immutable value

Instead of mutating the old object, you can represent the new requirement with a different value:

```java
// Snippet declaring a stable ordering key.
record Job(String id, int priority) {
}
```

Remove the old Job, then offer the new Job. The old value does not mutate in any other place that holds it.

This design separates two concerns: business state can continue changing, while the item placed in the heap has a stable priority key until it is replaced.

If a job has extensive mutable descriptive data, the queue item can hold just the id and a snapshot of the fields needed for comparison, while business data is managed in an appropriate store.

### 6.3. An update sequence needs a failure policy

Remove followed by offer is multi-step. A small example with valid numeric types and a simple comparator can keep the flow clear, but the API does not turn the sequence into a transaction.

If business rules require never losing a job when a later step fails, you need a proper preparation, recovery, and coordination workflow. Ignoring the boolean returned by remove can cause code to add a new entry even when the old one was not removed properly.

Do not paper over a lookup failure by offering the same mutated object anyway. Doing so can leave multiple occurrences of the same job.

## 7. Program 2: replacing an immutable Job

Save the file `ImmutablePriorityReplacementDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class ImmutablePriorityReplacementDemo {
    record Job(String id, int priority) {
        @Override
        public String toString() {
            return id + ":" + priority;
        }
    }

    static final Comparator<Job> ORDER =
            Comparator.comparingInt(Job::priority).thenComparing(Job::id);

    static Job replacePriority(
            PriorityQueue<Job> queue, Job oldJob, int newPriority) {
        Job replacement = new Job(oldJob.id(), newPriority);
        if (!queue.remove(oldJob)) {
            throw new IllegalStateException("Old job is not queued");
        }
        queue.offer(replacement);
        return replacement;
    }

    public static void main(String[] args) {
        Job a = new Job("A", 10);
        Job b = new Job("B", 20);
        Job oldC = new Job("C", 30);
        PriorityQueue<Job> queue = new PriorityQueue<>(ORDER);
        queue.addAll(List.of(a, b, oldC));

        Job newC = replacePriority(queue, oldC, 5);
        System.out.println("old immutable value = " + oldC);
        System.out.println("new immutable value = " + newC);
        System.out.println("size after replacement = " + queue.size());
        System.out.println("contains old value = " + queue.contains(oldC));
        System.out.println("contains new value = " + queue.contains(newC));
        System.out.println("head after replacement = " + queue.peek());

        try {
            replacePriority(queue, oldC, 1);
        } catch (IllegalStateException ex) {
            System.out.println("replace missing old value = "
                    + ex.getClass().getSimpleName());
        }
        System.out.println("size after rejected replacement = " + queue.size());

        List<String> output = new ArrayList<>();
        Job next;
        while ((next = queue.poll()) != null) {
            output.add(next.toString());
        }
        System.out.println("safe poll order = " + output);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 ImmutablePriorityReplacementDemo.java
java ImmutablePriorityReplacementDemo
```

Verification run output:

```text
old immutable value = C:30
new immutable value = C:5
size after replacement = 3
contains old value = false
contains new value = true
head after replacement = C:5
replace missing old value = IllegalStateException
size after rejected replacement = 3
safe poll order = [C:5, A:10, B:20]
```

### 7.1. The old value is not mutated

OldC remains C:30; newC is C:5. After replacement, the queue has three elements, no longer contains the old value, and contains the new value.

The head C:5 is accurate according to the comparator because it was inserted via offer as a valid new element.

The example has one Job per id, no duplicate records, and no concurrent updates. The helper verifies removal succeeded before adding.

### 7.2. Attempting to replace an old version is rejected

Calling the helper again with oldC after oldC has already been replaced will not find that value. The helper throws IllegalStateException and does not offer another replacement.

This is an important check for updates based on an old value: stale requests should not silently create extra work.

### 7.3. Correctness and cost are two separate questions

The poll output is C:5, A:10, B:20, matching the priorities of the new values.

However, the remove(oldC) step still performs a linear search. This pattern prioritizes lifecycle clarity and fits the example's constraints; it must not be advertised as a general O(log n) decrease-key/update-key operation.

## 8. Rebuilding the heap after multiple changes must be done intentionally

If multiple priority fields have already been mutated, one recovery path is to establish canonical data and build a new queue from those values.

Before doing so, ensure the data used for building does not keep changing while being read. Otherwise, the new structure could be built from different ordering relations at different moments.

A clear workflow:

```text
identify the canonical data source
    -> pause or coordinate related updates
    -> capture consistent snapshots of priority keys
    -> create a new PriorityQueue with the right comparator
    -> insert the snapshots using an appropriate build operation
    -> verify before switching usage to the new queue
```

### 8.1. Copying a PriorityQueue has no contract to repair a broken heap

A seemingly simple approach:

```java
// Do not treat this as a repair for a heap whose invariant is broken.
PriorityQueue<Task> repaired = new PriorityQueue<>(broken);
```

has no contract to re-evaluate all mutated priority keys.

In the [OpenJDK 17 PriorityQueue source](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java), the copy path from an object of exact class PriorityQueue can copy the backing array without re-heapifying. That optimization relies on the assumption that the source is already a valid heap.

Therefore, if the source's invariant was broken via setters, merely switching to a copy container does not automatically constitute a reliable recovery procedure.

Optimization details may vary across implementations or source types. The rule to keep is not to rely on the copy constructor as a repair API for misused state.

### 8.2. Adding to a new queue with an explicit comparator

A pattern to reorganize by current values is:

```java
// Snippet; currentValues is a stabilized data source.
PriorityQueue<Task> rebuilt = new PriorityQueue<>(order);
rebuilt.addAll(currentValues);
```

With the new queue, elements are added according to the chosen comparator. However, if they are still the same mutable Task instances, a subsequent mutation at the source can break rebuilt's invariant again.

Reorganizing positions and freezing priority keys are two distinct requirements.

### 8.3. Key snapshots help decouple lifecycles

You can build using a stable value type:

```java
// Declaration snippet; priority-identifying components are kept stable.
record QueueSnapshot(String id, int priority) {
}
```

When building the new queue, create a QueueSnapshot from each job's confirmed state. The comparator reads only those immutable components.

This keeps the new structure accurate according to the **captured snapshot**. It does not mean the queue automatically syncs with every subsequent priority update on the business object. If business priority changes, you still need a replacement request or an explicit versioning mechanism.

## 9. Program 3: direct copy, shared rebuild, and snapshot

Save the file `PriorityQueueRebuildDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class PriorityQueueRebuildDemo {
    static final class MutableTask {
        private final String id;
        private int priority;

        MutableTask(String id, int priority) {
            this.id = id;
            this.priority = priority;
        }

        int priority() {
            return priority;
        }

        @Override
        public String toString() {
            return id + ":" + priority;
        }
    }

    record Snapshot(String id, int priority) {
        @Override
        public String toString() {
            return id + ":" + priority;
        }
    }

    public static void main(String[] args) {
        Comparator<MutableTask> mutableOrder =
                Comparator.comparingInt(MutableTask::priority);
        MutableTask d = new MutableTask("D", 40);
        PriorityQueue<MutableTask> broken = new PriorityQueue<>(mutableOrder);
        broken.addAll(List.of(
                new MutableTask("A", 10),
                new MutableTask("B", 20),
                new MutableTask("C", 30),
                d,
                new MutableTask("E", 50)));
        d.priority = 1;

        PriorityQueue<MutableTask> directCopy = new PriorityQueue<>(broken);
        PriorityQueue<MutableTask> sharedRebuild =
                new PriorityQueue<>(mutableOrder);
        sharedRebuild.addAll(broken);

        Comparator<Snapshot> snapshotOrder =
                Comparator.comparingInt(Snapshot::priority)
                        .thenComparing(Snapshot::id);
        PriorityQueue<Snapshot> stable = new PriorityQueue<>(snapshotOrder);
        for (MutableTask task : broken) {
            stable.offer(new Snapshot(task.id, task.priority));
        }

        System.out.println("broken head = " + broken.peek());
        System.out.println("direct copy head = " + directCopy.peek());
        System.out.println("shared rebuild head = " + sharedRebuild.peek());
        System.out.println("snapshot rebuild head = " + stable.peek());

        d.priority = 100;
        System.out.println("shared rebuild after later change = "
                + sharedRebuild.peek());
        System.out.println("snapshot head after later change = " + stable.peek());

        List<String> output = new ArrayList<>();
        Snapshot next;
        while ((next = stable.poll()) != null) {
            output.add(next.toString());
        }
        System.out.println("snapshot poll order = " + output);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 PriorityQueueRebuildDemo.java
java PriorityQueueRebuildDemo
```

Verification run output:

```text
broken head = A:10
direct copy head = A:10
shared rebuild head = D:1
snapshot rebuild head = D:1
shared rebuild after later change = D:100
snapshot head after later change = D:1
snapshot poll order = [D:1, A:10, B:20, C:30, E:50]
```

The broken and directCopy sections are observations after a mutation intentionally breaking the invariant, verified in the stated environment. Do not treat a specific broken behavior as something every implementation must reproduce identically.

### 9.1. Direct copy still has head A:10

D was changed to D:1, yet broken.peek is still A:10. DirectCopy also has head A:10 in this run.

That illustrates how the copy path can trust the source's heap layout. There is no automatic repair call just because a constructor created a new object.

### 9.2. Rebuilding with addAll organizes by values at that moment

SharedRebuild is created empty with mutableOrder and then adds the existing references. Its head at that moment is D:1, matching current values.

However, D inside sharedRebuild is the exact same D object still held externally. When D's priority changes to 100, sharedRebuild's peek returns D:100, which is once again wrong compared to the waiting A:10.

One valid rebuild does not protect against future mutations if the key remains shared and mutable.

### 9.3. Snapshot preserves the recorded priority

Stable holds separate Snapshot instances, so D inside it remains D:1 when the original object changes to D:100. The poll sequence is D:1, A:10, B:20, C:30, E:50.

This proves the heap is stable with respect to the snapshot data; it does not prove that it automatically applied the latest D:100 business requirement.

If the new requirement is that D must be processed at priority 100, the application must replace the snapshot or invalidate the old version. Snapshot independence is a tool for managing change, not a substitute for propagating changes intentionally.

### 9.4. Build cost must be calculated based on how it is performed

In the example, the new queue has an explicit comparator and receives elements via offer or addAll. It can be analyzed as n insertions with a general O(n log n) bound for heap adjustments.

Batch heapify algorithms can achieve linear cost in suitable construction paths, but one must not infer that every copy constructor or every addAll is a desired heapify operation.

When the goal is accurate recovery, first establish the data and semantics. Only then choose a well-founded, efficient build method.

## 10. When updates are frequent: decouple queue items from business state

Calling remove(Object) every time can be too expensive if the number of jobs is large and priorities change continuously. You can consider an alternative model, while still keeping heap keys stable.

One approach is a versioned immutable queue entry:

```java
// Data type snippet, not a complete scheduler.
record QueueEntry(String taskId, int priority, long version) {
}
```

The idea:

1. Each job has a current active version managed in the canonical source.
2. When priority changes, create a new QueueEntry with the new priority and version.
3. The comparator reads only priority and the entry's immutable tie-breaking criteria.
4. When polling an entry, compare its version against the active version.
5. If the entry is stale, discard it; if still valid, process it according to application policy.

This mechanism does not mutate the key of an entry already in the heap. It replaces immediate search-and-remove with recognizing stale entries at consumption time.

### 10.1. Shifts the trade-off, does not make work vanish

Old entries still occupy space until they are polled or cleaned up. Heap cost depends on the total number of stored entries, including stale ones, not just the number of active jobs.

A single request to fetch a job may have to skip multiple stale entries. Therefore, do not claim that every business processing step is guaranteed to perform only a single O(log n) poll.

You need appropriate policies for cleanup, cancellation, version issuance, and storage bounds. If the API provides peek to inspect the next valid job, it must also handle stale heads; simply calling raw peek on a stale entry can lead to wrong decisions.

### 10.2. Canonical source and queue must coordinate

Updating the version in a Map and then adding an entry involves multiple steps. In a multithreaded system, design the relationship between them so half-finished state is never exposed.

Do not copy this conceptual description verbatim as a complete concurrent structure. It is a pattern for separating immutable keys from current validity, which must be implemented to fit specific requirements.

Another approach is a heap structure that supports key updates via explicit index/handle. When using such an API, read its specific contract; standard PriorityQueue does not provide that capability merely by holding a reference to an element.

## 11. Indirect updates and multiple threads cannot be fixed by locks alone

### 11.1. Comparator reads external state

Suppose the comparator does not read task.priority, but instead looks up `priorities.get(task.id)` in a Map. The Task object may be immutable, yet the ordering relation still changes when the Map is updated.

Or an external flag switches from "smaller number first" to "larger number first". The existing heap tree is not reorganized just because that flag changed.

When auditing risk, trace all data the comparator reads, not just setters in the element class.

### 11.2. Volatile or an atomic field does not perform sift

A mechanism that makes a new priority value visible does not automatically move the item in the heap.

A situation can occur where every comparison reads the new value accurately, yet the layout built under the old value remains wrong. Therefore, cross-thread data visibility and structural maintenance must be solved separately.

### 11.3. Synchronization only helps when it properly guards the entire change

If one thread holds a lock during offer/poll while another thread directly mutates priority without following the same protocol, the invariant can still be broken.

Even if all operations run sequentially under the same lock, a setter executed while the element is still in the queue still does not re-sort the heap. Locks only prevent interleaved updates; the updating thread must still remove/replace/rebuild properly.

Similarly, switching to a concurrent collection does not automatically create a setter listener for objects inside it. Explicit priority update semantics must be preserved.

### 11.4. One object in multiple queues

If the same Task sits in two PriorityQueues under the same or different criteria, mutating Task can affect both.

Removing from the first queue before the setter does not protect the second queue. Separating each queue item into its own key/snapshot usually helps clarify which structure must be updated and when.

Snapshots in multiple places also need a change-propagation mechanism if the goal is to keep them reflecting the same business version. Immutability does not mean automatic data synchronization.

## 12. Choosing an approach by scenario

| Scenario | Approach to consider | Points to verify |
|---|---|---|
| Priority does not change while waiting | Immutable entry | Comparator and tie-breakers are all stable |
| Occasional single-job change at moderate scale | Remove old value then offer new value | Identity, duplicates, remove success, O(n) cost |
| Many keys mutated or ranking rules changed | Fetch canonical data and build a new structure | Consistent snapshot, right comparator, do not trust copying a broken heap |
| Very frequent updates | Versioned entry or structure supporting update-key | Stale entries, memory, total cost, and atomicity |
| One object indexed in multiple places | Separate keys per structure | Do not let a shared setter silently alter all indexes |
| Shared multithreaded processing needed | Design both update model and coordination | Synchronization does not replace heap maintenance |

Not every state change on a job breaks the queue. If the comparator only reads priority and a stable id, editing a note that does not participate in ordering may not affect the heap.

However, when id is used as a tie-breaker, id itself belongs to the data that must remain stable. List all comparison components completely, not just the field named priority.

A sound choice should be able to specify: who has permission to change it, what state the element is in when the change occurs, and what operation maintains the structure afterward.

## 13. Fixes that easily introduce more bugs

| Approach | What is still wrong | How to handle |
|---|---|---|
| Set priority and expect peek to find min | Peek only reads the already-maintained head | Use an explicit update |
| Poll once to "refresh" everything | Poll repairs one path, assuming the heap is valid | Do not use as a general repair |
| Re-offer the same mutated object | Can create duplicate occurrences of the same reference | Control identity and remove properly before replacing |
| See contains is true and conclude queue is right | Membership and order are two different questions | Check head selection and poll sequence |
| Assume remove(Object) after mutation always loses track | Lookup by equals can still succeed | Distinguish membership lookup from heap maintenance |
| Remove once when there are multiple occurrences | Remaining references are still affected by setters | Manage multiplicity or use separate entries |
| Copy broken heap via constructor | Some copy paths do not re-heapify | Build from canonical data with a clear process |
| Rebuild with the same objects then keep calling setters | The new heap can break again | Protect keys or use immutable snapshots |
| Use a record containing a mutable priority object | Immutability is only on the direct reference | Audit nested data read by the comparator |
| Use synchronized/volatile as a sorting mechanism | Memory mechanisms do not perform sift | Coordinate properly and preserve structural update flow |
| Call remove-then-offer O(log n) | Lookup by object can be O(n) | Account for all steps |
| Snapshot does not change so assume it is always latest priority | Snapshot holds data at creation time | Propagate replacement requests or new versions |

Do not use a small dataset that happens to produce the right result to justify a mutation path that violates invariants. Risks usually surface when the mutated element sits deeper, update order shifts, or more objects are involved.

## 14. Testing bugs and solutions across the lifecycle

Tests should follow realistic operation sequences, not just test the comparator on two static objects.

### 14.1. Before mutation

Confirm the initial queue is valid per requirements:

- Peek returns the right head element.
- Priority data has distinct values to avoid confusion with ties.
- Job counts and identities are clear.
- Comparator has a stable rule.

If equal priorities are needed, add a separate case for the designed tie-breaker. Do not use an unguaranteed tie order to conclude whether a mutation bug exists.

### 14.2. Mutating at different positions

Test:

- A non-head element changed to a value that should move it forward.
- The head element changed to a value that should move it back.
- Multiple jobs changing priority.
- An object with multiple references or multiple occurrences.
- Comparison data changing via nested objects or external config.

Experiments that intentionally call setters inside the queue help reproduce the risk; they are not broken behavior that an application should rely on as a stable API.

### 14.3. Verifying valid solutions

For replacement or snapshot-rebuild flows:

1. Verify the old version is removed or invalidated properly.
2. Verify the new version is present the exact number of times expected.
3. Verify peek after the update.
4. Poll all elements on test data to verify the expected order.
5. Verify stale update requests are handled properly.
6. Verify subsequent source changes affect or do not affect the snapshot as designed.

Expected data must reflect the chosen model. For snapshots, results are accurate to the captured version; for "always latest" requirements, both version updates and stale-data filtering are needed.

### 14.4. Do not check only size or contains

A queue can retain all objects while still selecting the wrong order. Size and contains do not replace checking the head and processing sequence.

PriorityQueue's iterator also does not guarantee priority-order traversal even when the heap is valid. To compare the processing sequence, poll from a valid test queue or a properly constructed dataset.

Do not use a Set to verify results if both order and multiplicity matter.

## 15. Practice exercises

### Exercise 1: mutating a lower element

The queue holds A:10, B:20, C:30. Change C to C:1 via a setter. Why might peek still return A?

**Answer hint:** the setter changes the value inside the object but does not move item C up to its proper position. The old root remains there and peek does not rescan for the minimum.

### Exercise 2: mutating the root

If A:10 at the head changes to A:100, does the heap need to be reconsidered?

**Answer hint:** yes. A may need to move down; mutating the field does not automatically sift-down.

### Exercise 3: contains is still true

A test shows contains(task) returns true after changing priority. Does that prove the processing order is still right?

**Answer hint:** no. Contains checks existence via equals; the heap selects the head via comparator. Those are two different requirements.

### Exercise 4: the same reference added twice

Remove task once, change its priority, and re-add it. Are all items in the queue guaranteed to be valid?

**Answer hint:** no. Another occurrence of the same reference may still be in the queue and affected by the setter. You need to manage multiplicity or use separate stable entries.

### Exercise 5: copy constructor

The queue lost its invariant after mutation. Should `new PriorityQueue<>(broken)` be treated as a guaranteed fix?

**Answer hint:** no. Implementation paths can copy the layout without re-heapifying, assuming the source is valid. You must build intentionally from canonical data.

### Exercise 6: snapshot holds D:1

After creating snapshot D:1, the business object changes to D:100. Does the snapshot still returning D:1 prove it updated to the latest priority?

**Answer hint:** no. It is stable to the captured version. Reflecting 100 requires a replacement request or a versioning mechanism.

### Exercise 7: is remove then offer logarithmic?

Since offer and heap-head operations are O(log n), can we conclude that updating an object via remove(Object) then offer is also O(log n)?

**Answer hint:** no. Remove(Object) can perform an O(n) linear search, which must be accounted for.

### Exercise 8: changing only a note

The comparator does not read the note, and all other comparison keys remain unchanged. Does editing the note automatically break the heap?

**Answer hint:** not necessarily. The risk under discussion comes from changing the comparison relation. You must check the exact data the comparator actually reads.

A controllable priority design preserves two things at once: keys inside the heap are stable, and all business changes go through an explicit update workflow. When that holds, head selection never depends on a setter firing silently outside the structure.
