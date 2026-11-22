# Tied Elements, Stability, and Tie-Breaker Keys

## 1. The problem: when priorities are equal, who goes first?

A system receives three jobs A, B, and C in that exact order. All three have priority 2. When using `PriorityQueue`, a programmer might expect A, then B, then C to be polled, since there is no difference in priority.

However, that expectation is not yet expressed in the comparison rule.

If the comparator only inspects priority, it only states that A, B, and C are **tied**. It does not specify who should be chosen first within that group. `PriorityQueue` does not automatically add a "first-come, first-served" rule for tied elements.

This lesson addresses three questions:

- When are two elements considered tied?
- Why is a priority queue not inherently stable?
- How do you use a tie-breaker key to achieve first-come, first-served order within each priority group?

The goal is to write a complete head-selection rule and be able to verify it. The examples use Java 17+, run on a single thread, and keep comparison keys unchanged while elements are in the queue.

## 2. Ties are defined by comparison

### 2.1. What does compare returning 0 mean?

Suppose a job has a name and a priority. The convention in this example is that a smaller priority number is processed first:

```java
// Illustrative declarations placed inside a class:
record Job(String name, int priority) {}

Comparator<Job> byPriority = Comparator.comparingInt(Job::priority);
```

You need to import `java.util.Comparator`. For `Job("A", 2)` and `Job("B", 2)`, the comparator returns 0 because it only reads the `priority` field.

Four jobs can be divided into groups:

| Job | Priority | Relationship determined by the comparator |
| --- | --- | --- |
| urgent | 1 | Precedes every priority-2 job |
| A | 2 | Tied with B and C |
| B | 2 | Tied with A and C |
| C | 2 | Tied with A and B |

Within the priority-2 group, the current comparator does not choose A, B, or C first. The order between groups is defined; the order within a group is not yet distinguished.

If natural ordering via `Comparable` is used, the same tie relationship comes from `compareTo(...) == 0`. It does not have to come from a separately passed comparator.

### 2.2. A tie is not necessarily equality under equals

Two Jobs with different names but the same priority can satisfy:

```text
compare(A, B) == 0
A.equals(B) == false
```

The `Job` record compares both `name` and `priority` in its default equality check. The comparator above only inspects one field. The two relationships answer two different questions:

| Relationship | Question |
| --- | --- |
| `compare(a, b) == 0` | Do the two elements have the same rank under this ordering rule? |
| `a.equals(b)` | Are the two objects equal according to the data model? |
| `a == b` | Do the two references point to the same object? |

Do not substitute one of these three questions for another.

For `PriorityQueue`, a tie does not mean the second element is discarded. The queue can still hold multiple objects of the same rank, multiple equal objects, or multiple occurrences of the same reference.

### 2.3. Object-based lookup and removal still use equality

`contains(Object)` and `remove(Object)` search using object equality. They do not use "same priority" as the definition of a match.

If the queue contains A with priority 2, searching for a Job X with priority 2 will not necessarily return `true`. If Job equality checks both name and priority, X differs from A and therefore does not match.

The class contract regarding ties, retaining elements, and object-based operations is described in [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

## 3. Stability: preserving relative order among tied elements

### 3.1. Stability is an additional requirement

In this context, the desired "stability" means: if two job submissions have the same priority, the one accepted earlier must be polled earlier.

For example, inserting in this order:

```text
A priority 2 → urgent priority 1 → B priority 2 → C priority 2
```

A polling order that satisfies both priority and FIFO within each group is:

```text
urgent → A → B → C
```

This is not queue-wide FIFO: urgent arrived after A, yet it is still processed first because its priority is better. First-come, first-served only arbitrates among elements that tie on the primary criterion.

### 3.2. PriorityQueue does not guarantee FIFO within a group

If multiple elements tie as the smallest under the active ordering, the head of the queue may be any one of them. There is no guarantee of choosing by insertion order.

Some inputs may still happen to produce arrival order. That only shows that particular run matched; it does not prove the queue has a stability contract.

Nor should you rephrase this as "PriorityQueue always reverses tied elements" or "always randomizes them". Neither is a rule guaranteed by the class.

### 3.3. Why can a heap change the positions of tied elements?

Consider a heap model with three jobs of the same priority:

```text
        A:2
       /   \
     B:2   C:2
```

After polling A, one way to maintain the heap moves the last element C to the root:

```text
        C:2
       /
     B:2
```

Because C and B compare as 0, the heap property still holds. The heap has no information that B was added before C, so there is no condition forcing C to be swapped below B.

A valid implementation can therefore poll A, C, B. This illustrates why the heap invariant and insertion-history stability are two different requirements; it is not a layout promise that every JDK must use.

## 4. Observation program: tied elements can still change order

Save as **EqualPriorityObservation.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class EqualPriorityObservation {
    record Job(String name, int priority) {}

    private static List<String> pollNames(PriorityQueue<Job> queue) {
        List<String> names = new ArrayList<>();
        while (!queue.isEmpty()) {
            names.add(queue.poll().name());
        }
        return names;
    }

    public static void main(String[] args) {
        Comparator<Job> byPriority = Comparator.comparingInt(Job::priority);
        Job a = new Job("A", 2);
        Job b = new Job("B", 2);
        Job c = new Job("C", 2);

        System.out.println("compare A and B: " + byPriority.compare(a, b));
        System.out.println("A equals B: " + a.equals(b));

        PriorityQueue<Job> observation = new PriorityQueue<>(byPriority);
        observation.addAll(List.of(a, b, c));
        System.out.println("inserted names: [A, B, C]");
        System.out.println("observed tied poll order: " + pollNames(observation));

        PriorityQueue<Job> lookup = new PriorityQueue<>(byPriority);
        lookup.addAll(List.of(a, b, c));
        System.out.println("size with three ties: " + lookup.size());
        System.out.println("contains equal B: " + lookup.contains(new Job("B", 2)));
        System.out.println("contains same-priority X: " + lookup.contains(new Job("X", 2)));
        System.out.println("remove same-priority X: " + lookup.remove(new Job("X", 2)));
        System.out.println("remove equal B: " + lookup.remove(new Job("B", 2)));
        System.out.println("size after removing B: " + lookup.size());

        PriorityQueue<Job> duplicates = new PriorityQueue<>(byPriority);
        duplicates.offer(a);
        duplicates.offer(a);
        System.out.println("same reference twice size: " + duplicates.size());
        System.out.println("same reference twice names: " + pollNames(duplicates));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 EqualPriorityObservation.java
java EqualPriorityObservation
```

The program was compiled with `--release 17` and run on OpenJDK 24.0.2. Observed stdout:

```text
compare A and B: 0
A equals B: false
inserted names: [A, B, C]
observed tied poll order: [A, C, B]
size with three ties: 3
contains equal B: true
contains same-priority X: false
remove same-priority X: false
remove equal B: true
size after removing B: 2
same reference twice size: 2
same reference twice names: [A, A]
```

The `observed tied poll order` line records the actual result in that environment, not a fixed order guaranteed by the API across all Java 17+ runtimes. The `--release 17` flag checks the target language/API and generates corresponding bytecode; the JVM running the example is still the version noted above.

Key takeaways from the output:

- A and B are tied, yet they are not equal according to the record.
- All three tied elements are retained.
- The observed order A, C, B is a counterexample to assuming automatic FIFO.
- Creating another Job equal to B still finds and removes B.
- Creating a Job with a different name but the same priority does not cause `contains` or `remove` to treat it as present.
- Adding the same reference twice creates two occurrences rather than deduplicating.

Do not write tests requiring the exact order A, C, B to describe PriorityQueue's contract. Without a secondary criterion, the identity order within a tied group is unspecified.

## 5. A tie-breaker key turns an implicit wish into an explicit rule

### 5.1. From a single key to a composite key

If FIFO within each group is needed, assign each accepted submission an increasing sequence number:

```text
submission key = (priority level, reception sequence number)
```

Compare from left to right:

1. If the priority levels differ, use the priority level to decide.
2. If the priority levels are equal, use the sequence number.
3. Only tie completely if all considered criteria tie.

Example:

| Submission | Priority | Sequence | Expected poll order |
| --- | --- | --- | --- |
| A | 2 | 0 | After urgent, before B |
| urgent | 1 | 1 | First |
| B | 2 | 2 | After A, before C |
| C | 2 | 3 | Last in priority-2 group |

The keys `(2,0)`, `(1,1)`, `(2,2)`, `(2,3)` yield the order `(1,1)`, `(2,0)`, `(2,2)`, `(2,3)`.

When the sequence numbers distinguish all submissions still in the queue, two submissions with the same priority are no longer tied under the **complete comparator**. The heap does not need to remember history on its own; the necessary history has become part of the key.

### 5.2. Chaining with thenComparingLong

A direct data model:

```java
// Illustrative declarations placed inside a class:
record QueuedJob(String name, int priority, long receivedOrder) {}

Comparator<QueuedJob> order =
        Comparator.comparingInt(QueuedJob::priority)
                  .thenComparingLong(QueuedJob::receivedOrder);
```

`thenComparingLong` is only consulted when the preceding criterion ties. Do not add the two values together into a single combined score.

For instance, do not write `priority + receivedOrder` and compare that, because a large sequence number could overturn the priority decision. The rule "priority is primary, sequence number only breaks ties" must be preserved by comparing keys sequentially.

### 5.3. Reversing the right criterion

If a higher priority number should be processed first, while a smaller sequence number still goes first on a tie:

```java
Comparator<QueuedJob> higherPriorityFirst =
        Comparator.comparingInt(QueuedJob::priority)
                  .reversed()
                  .thenComparingLong(QueuedJob::receivedOrder);
```

If instead you write:

```java
// Differs from the requirement: also reverses the reception order.
Comparator<QueuedJob> reversedEverything =
        Comparator.comparingInt(QueuedJob::priority)
                  .thenComparingLong(QueuedJob::receivedOrder)
                  .reversed();
```

then the tie-breaker criterion is reversed as well. Within the same priority group, the submission with the larger sequence number will go first.

Sign rules, transitivity, and chaining criteria are described in [Comparator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

## 6. Put the sequence number on the job or on the submission?

### 6.1. One object can be submitted multiple times

If you attach a fixed sequence number to the job itself and then add the same object again, the two occurrences may share the same tie-breaker key. They then tie again under the complete comparator.

The question to answer is: are you ordering **jobs** or **job submissions**?

For per-group FIFO by submission, the sequence number usually belongs on an enclosing wrapper record:

```text
Entry {
    value: job,
    sequence: number of this submission
}
```

The same `value` can appear in multiple Entries, each with a different sequence. The data structure does not automatically discard resubmissions just because their payloads are identical.

### 6.2. When the number is assigned is part of the contract

In the single-threaded example, each valid `offer` call assigns the next number immediately upon accepting the job. Because all calls occur sequentially, a smaller number corresponds to an earlier acceptance.

If an application assigns sequence numbers from a list of jobs that was already sorted beforehand, those numbers describe the list traversal order, not the lost original history.

If data is reloaded from storage, you must decide whether to preserve the old reception numbers or treat reloading as new submissions. Do not name a field `sequence` and assume it automatically carries every temporal meaning you need.

## 7. Runnable program: wrapping jobs with a reception-order key

Save as **StablePriorityQueueDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class StablePriorityQueueDemo {
    record Job(String name, int priority) {}
    private record Entry<E>(E value, long sequence) {}

    static final class StableQueue<E> {
        private final PriorityQueue<Entry<E>> entries;
        private long nextSequence;

        StableQueue(Comparator<? super E> byPriority) {
            Objects.requireNonNull(byPriority);
            entries = new PriorityQueue<>((left, right) -> {
                int result = byPriority.compare(left.value(), right.value());
                return result != 0
                        ? result
                        : Long.compare(left.sequence(), right.sequence());
            });
        }

        void offer(E value) {
            Objects.requireNonNull(value);
            if (nextSequence == Long.MAX_VALUE) {
                throw new IllegalStateException("sequence exhausted");
            }
            entries.offer(new Entry<>(value, nextSequence));
            nextSequence++;
        }

        E peek() {
            Entry<E> head = entries.peek();
            return head == null ? null : head.value();
        }

        E poll() {
            Entry<E> head = entries.poll();
            return head == null ? null : head.value();
        }

        int size() {
            return entries.size();
        }

        boolean isEmpty() {
            return entries.isEmpty();
        }
    }

    private static List<String> pollNames(StableQueue<Job> queue) {
        List<String> result = new ArrayList<>();
        while (!queue.isEmpty()) {
            result.add(queue.poll().name());
        }
        return result;
    }

    public static void main(String[] args) {
        StableQueue<Job> queue =
                new StableQueue<>(Comparator.comparingInt(Job::priority));
        queue.offer(new Job("slow-A", 3));
        queue.offer(new Job("urgent-A", 1));
        queue.offer(new Job("normal", 2));
        queue.offer(new Job("urgent-B", 1));
        queue.offer(new Job("slow-B", 3));
        queue.offer(new Job("urgent-C", 1));

        System.out.println("size: " + queue.size());
        System.out.println("head: " + queue.peek().name());
        System.out.println("stable poll names: " + pollNames(queue));

        Job a = new Job("A", 1);
        queue.offer(a);
        queue.offer(new Job("B", 1));
        System.out.println("removed before resubmit: " + queue.poll().name());
        queue.offer(a);
        System.out.println("after resubmit names: " + pollNames(queue));

        queue.offer(a);
        queue.offer(a);
        System.out.println("duplicate payload size: " + queue.size());
        System.out.println("duplicate payload names: " + pollNames(queue));
        System.out.println("empty peek: " + queue.peek());
        System.out.println("empty poll: " + queue.poll());
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 StablePriorityQueueDemo.java
java StablePriorityQueueDemo
```

Exact stdout:

```text
size: 6
head: urgent-A
stable poll names: [urgent-A, urgent-B, urgent-C, normal, slow-A, slow-B]
removed before resubmit: A
after resubmit names: [B, A]
duplicate payload size: 2
duplicate payload names: [A, A]
empty peek: null
empty poll: null
```

`StableQueue` in the example is a small class illustrating a single-threaded policy, not a full implementation of the `Queue` interface. The methods it provides express the core goal: accepting elements, inspecting/polling the head, and checking size.

The Entry wrapper establishes that the sequence belongs to the **submission**, while Job holds the job data. Entry's comparator first delegates priority comparison to `byPriority`; only on a tie does it compare sequence.

`Objects.requireNonNull` rejects null payloads. Therefore, null returned from `peek()` or `poll()` unambiguously means an empty queue, without confusion with a waiting null job.

The code blocks acceptance when the next sequence reaches `Long.MAX_VALUE`, before the counter could wrap around. This policy deliberately leaves that final value unused; it chooses to report exhaustion rather than silently produce wrong ordering keys.

## 8. Reading the output group by group

The first six calls assign these numbers:

| Job | Priority | Sequence | Comparison key |
| --- | --- | --- | --- |
| slow-A | 3 | 0 | `(3,0)` |
| urgent-A | 1 | 1 | `(1,1)` |
| normal | 2 | 2 | `(2,2)` |
| urgent-B | 1 | 3 | `(1,3)` |
| slow-B | 3 | 4 | `(3,4)` |
| urgent-C | 1 | 5 | `(1,5)` |

When polled:

```text
Priority group 1: urgent-A → urgent-B → urgent-C
Priority group 2: normal
Priority group 3: slow-A → slow-B
```

slow-A was submitted first, yet it does not stand at the front of the whole queue because priority 3 is lower priority than 1 and 2 under this convention. Within priority group 3, slow-A still precedes slow-B.

The resubmission of A illustrates another policy that should be stated explicitly:

```text
accept A → accept B → poll A → accept A again
```

Afterward, B must go before the new A submission, so the output is `[B, A]`. The A object may still be the same reference, but the new Entry receives a new sequence number.

The class does not reset the counter to 0 whenever the queue becomes empty. This keeps the acceptance model simple without needing to manage number collisions. If another design wants to reuse numbers, it must ensure it does not generate keys that collide with submissions that are still relevant.

## 9. Choosing a tie-breaker key that matches business meaning

### 9.1. A tie-breaker key does not necessarily mean FIFO

| Tie-breaker key | Policy it can express | Does it automatically guarantee FIFO? |
| --- | --- | --- |
| Increasing reception sequence number | First-come, first-served within the same group | Yes, if assigned properly and sufficiently distinct |
| Deadline | Earlier due job within the same group | Not necessarily |
| Job name | Lexicographical order of names | No |
| Unique ID | A deterministic order by ID | Not necessarily |
| Timestamp | Order by recorded time value | Not enough if timestamps collide or do not match acceptance order |

A tie-breaker key picks a winner when the preceding criterion ties. Which key to choose is a business decision, not a technical trick with one answer for every application.

A unique ID distinguishes two jobs, but it does not inherently say which job arrived first. A timestamp can collide across multiple submissions; a clock source can also have resolution limits or adjustments.

If the business truly requires "priority, then deadline, finally arrival order", the comparator must evaluate those exact three criteria in that order. In that case, sequence only arbitrates when both priority and deadline tie.

### 9.2. Ties can still happen on the final criterion

Two Entries with the same priority and the same sequence can still compare as 0. Calling something a "tie-breaker key" does not automatically make the key unique.

If you require a deterministic order among all submissions still in the queue, you need a final criterion that distinguishes them or an explicit policy for remaining ties. The StableQueue example achieves this using non-repeating sequence numbers across accepted calls.

Do not use random numbers to express "first-come, first-served". Do not use `System.identityHashCode` as if it were reception history or a guaranteed unique ID. Neither value carries the FIFO contract the application needs.

### 9.3. Keep keys stable while waiting

If priority or sequence is mutated directly after an Entry is already in the heap, its current position may no longer be valid. The queue does not track arbitrary field assignments to repair its structure automatically.

Use immutable key data or update through a workflow that removes the old element and inserts the new value. Changing priority also raises a design question: keep the original reception order or assign a new sequence number? Both can be valid in different business domains, but the choice must be explicit.

In the example, the Entry record keeps sequence immutable; Job contains String and int, which are also immutable. Another payload with mutable fields still needs its own rules if the comparator reads those fields.

## 10. A comparator must be a consistent rule

### 10.1. Do not build a tie-breaker by subtracting and casting

Example to avoid when sequence is a long:

```java
// Incorrect comparison example:
int result = (int) (left.sequence() - right.sequence());
```

Subtraction can overflow; casting from long to int can also lose information. The magnitude of the difference is irrelevant to returning the comparison sign.

Use:

```java
int result = Long.compare(left.sequence(), right.sequence());
```

For an int priority, use `Integer.compare` or `Comparator.comparingInt`. Do not write `a.priority() - b.priority()` if you want the rule to hold across the entire int range.

### 10.2. Do not compute secondary order from state that changes on every call

A comparator must define a consistent relation while the keys are active. Approaches like "if tied, increment a counter inside compare" or "if tied, pick randomly" do not encode reception history.

A comparator can be called multiple times for the same pair, at different times and in opposite argument orders. Generate the sequence in `offer`, store it in Entry, and only read it in `compare`. Do not generate a new sequence each time two elements are compared.

If a comparator lacks transitivity or fails to flip sign properly when arguments are swapped, the heap has no valid order to maintain. Adding more keys cannot fix a comparison rule that is self-contradictory.

## 11. Stable sort and stable PriorityQueue are different contracts

`List.sort` has a stable sorting contract: elements the comparator considers tied preserve their relative order from the input. See [List.sort Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

However, if the input list comes from PriorityQueue's iterator, that order is not guaranteed to be reception history. A stable sort only preserves the input order it sees; it cannot recover history that was never stored.

Example:

```text
Reception history:             A, B, C
Input list from one traversal: A, C, B
All three have the same priority
Stable sort by priority only:
                               A, C, B
```

There is no contradiction: the sort was stable with respect to the input list, while that list did not represent the desired FIFO order.

When using a sequence tie-breaker key, polling with `poll()` yields the expected order. A list sorted with the same complete comparator also yields the same order for Entries whose keys are sufficiently distinct.

PriorityQueue's iterator still does not traverse in priority order after adding a sequence key. The tie-breaker fixes head selection; it does not change the iterator's contract. If you need to view elements in poll order, copy and poll, or build a list and sort it with the exact same comparator.

## 12. Single-threaded, multi-threaded, and what "first-come" means

The StableQueue example uses a plain long counter and a plain PriorityQueue. It is designed for a single thread. Replacing the counter with `AtomicLong` does not automatically make PriorityQueue thread-safe.

Even when using an appropriate concurrent queue structure, you must clarify which order is being recorded. For example:

```text
Thread A gets sequence 10 and is paused.
Thread B gets sequence 11 and adds to the queue first.
Thread A adds sequence 10 afterward.
```

The number-assignment order is A before B; the insertion-completion order is B before A. You must not call both the same "arrival order" without defining the acceptance point.

If B has already been polled before A actually appears in the queue, a smaller sequence added later cannot redo processing that has already happened. Priority rules apply to elements currently waiting, not to reordering the past.

`PriorityBlockingQueue` also does not guarantee order among equal-priority elements by default; its documentation suggests using a tie-breaker key when arbitration is needed. See [PriorityBlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html).

Concurrent acceptance design requires choosing the ordering point and proper synchronization mechanisms. This section marks the boundary of the example; do not treat the single-threaded StableQueue class as a complete concurrent scheduler.

## 13. Testing what needs to be guaranteed

### 13.1. When only a priority comparator is present

Do not require a specific identity order for a tied group. You can verify:

- Polled priority levels do not violate the ordering rule.
- No occurrences are lost or spuriously created.
- Elements in different groups obey the primary criterion.
- Object-based lookup/removal operations use the proper equality model.

Seeing A, B, C in one run is not enough to prove stability; seeing A, C, B does not mean data was corrupted.

### 13.2. When a sequence key is present

You can test stronger properties:

- Within the same priority, polled sequences increase according to the chosen policy.
- Priority remains the primary criterion; sequence does not override it.
- Each new submission receives an appropriate tie-breaker key, even for the same payload.
- Resubmitting a job behaves according to the rule of keeping the old number or assigning a new one.
- When all elements tie on priority, reception order is still preserved.
- Values near numeric limits do not cause the comparator to flip signs incorrectly.

Useful edge cases include an empty queue, a single element, multiple elements of the same priority, interleaved priorities, submitting the same reference multiple times, and polling then resubmitting.

A wrapper class can hide Entry so callers only see the payload; when testing stability, you can use distinct labels per submission to verify whether they are polled in the right order. Identical payloads make it impossible to observe submission identities from printed strings alone.

## 14. Common mistakes and how to fix them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Assuming equal priority is automatically FIFO | The comparator does not record insertion history | Add a reception key |
| Assuming compare returning 0 discards the later element | PriorityQueue is not a set | Distinguish order ties from deduplication |
| Using equals to predict who is at the head | Equals does not determine heap order | Inspect the complete comparator |
| Attaching the same sequence to two submissions | The two submissions can still tie | Assign the key per acceptance |
| Using a timestamp as a guaranteed unique key | Timestamps can collide | Have a sufficiently distinct final criterion |
| Adding priority and sequence together | The tie-breaker can override the primary criterion | Compare sequentially with thenComparing |
| Reversing the entire composite comparator | Also reverses FIFO order within groups | Reverse only the criterion that needs reversing |
| Generating sequence inside compare | Results depend on comparison count | Assign the number on acceptance and keep it immutable |
| Casting a long difference to int | Loses sign or information | Use Long.compare |
| Stable-sorting from iterator to recover FIFO | Arrival history is not in the iterator | Store the sequence at the source |
| Adding AtomicLong and sharing PriorityQueue | Counter and structure have separate synchronization needs | Design concurrent acceptance explicitly |

## 15. Self-check exercises with solutions

### Exercise 1: Three relationships

A and B are two Job records with different names and the same priority 2. The comparator only checks priority. What can `compare(A,B)`, `A.equals(B)`, and `A == B` be respectively?

**Solution:** 0, false, false. A tie does not mean full data equality or the same reference. PriorityQueue can still hold both.

### Exercise 2: Head selection in a tied group

Add A, B, and C with the same priority to a PriorityQueue that only compares priority. One run polls A, C, B. Is this an API violation?

**Solution:** No. All three are tied, and the class does not guarantee FIFO within a group. Nor should you turn this outcome into a fixed order expected across all runs.

### Exercise 3: Comparing composite keys

Submissions have keys `A=(2,0)`, `B=(1,1)`, `C=(2,2)`, `D=(1,3)`. Smaller priority goes first; on a tie, smaller sequence goes first. What is the poll order?

**Solution:** B, D, A, C. The primary criterion selects the priority-1 group first; within that group, 1 precedes 3. Next, the priority-2 group has 0 before 2.

### Exercise 4: Reversing order

You need larger priority first and smaller sequence first. Are "reverse priority then chain sequence" and "chain both then reverse" equivalent?

**Solution:** No. The latter also reverses sequence, so within the same priority it will poll the larger sequence number first. You must reverse the priority criterion before chaining ascending sequence.

### Exercise 5: Resubmitting the same object

A and B have the same priority and are accepted in order A then B. Poll A, then resubmit A using the lesson's StableQueue class. Who goes first next?

**Solution:** B. The resubmission of A gets a new Entry and a new sequence. If the business wants to preserve the old waiting age, that is a different policy that must be designed separately.

### Exercise 6: Name as tie-breaker

Does using `thenComparing(Job::name)` create FIFO within a group?

**Solution:** No. It creates name order when priorities tie. A can precede B because of its name even if B arrived first. If you want FIFO, the tie-breaker key must record reception order.

### Exercise 7: Stable sort

A list is read from a PriorityQueue in the order A, C, B; all three have the same priority. Must a stable sort by priority only return A, B, C?

**Solution:** No. It keeps the input's A, C, B. Sort stability does not recover insertion history from another structure.

### Exercise 8: Two ordering points in multithreading

A is assigned sequence 10 but has not been added to the queue yet. B is assigned sequence 11 and is added first. Is "A arrived first" a clear enough statement?

**Solution:** Not clear enough. You must specify whether you mean number-assignment order, acceptance start or completion order, or a specific synchronization point. A tie-breaker key is only meaningful when the application defines which order it records.

## 16. Reference documentation

- [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html): priority tie contract and object-based operations.
- [Comparator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): comparison operations and chaining criteria.
- [List.sort Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)): stability contract of list sorting.
- [PriorityBlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html): ordering limits among equal-priority elements and the tie-breaker key approach.

When you want a specific order within a tied group, record the arbitration data in the key and compare it explicitly. For submission-order FIFO, the sequence is stored history for the comparator to use, not a spontaneous property of a heap.
