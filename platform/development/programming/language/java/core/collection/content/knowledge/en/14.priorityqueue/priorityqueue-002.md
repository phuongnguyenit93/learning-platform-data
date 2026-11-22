# Natural Ordering and Custom Comparator

## 1. Which Element Does PriorityQueue Pick Next?

Suppose a program receives the numbers `6, 2, 9, 1, 5`. With a FIFO queue, the number 6 that arrived first would be retrieved first. If the requirement is to always retrieve the smallest available value, FIFO does not accurately model the task.

`PriorityQueue` maintains a queue head according to a **priority rule**. That rule can be the natural ordering of the element type or a `Comparator` that you supply.

The exact point to keep in mind is: the head of the queue is the **smallest element according to the comparison rule in use**. With the natural ordering of integers, that is the smallest number. With a reversed comparator, it is instead the numerically largest number.

There is no universal concept of "high priority" for all data. A high score might need to be processed first, whereas an early deadline usually has a smaller timestamp value. The comparator must translate business meaning into a concrete ordering.

This lesson progresses from integers to job objects, handles ties in priority, and verifies the retrieval order. The examples use APIs available in Java 17.

You need to know how to create objects, declare generic types, and use loops. `Comparable`, `Comparator`, and the meaning of comparison results are introduced before appearing in the full program.

## 2. Natural Ordering Comes from the Element Type

Natural ordering is provided by the element type via `Comparable<T>`, with the `compareTo` method.

When reading `a.compareTo(b)`:

| Result | Meaning in the type's ordering |
| --- | --- |
| Less than 0 | a comes before b |
| Equal to 0 | a and b are at the same ordering level |
| Greater than 0 | a comes after b |

Only the negative, 0, or positive sign carries the general meaning. A valid comparison is not required to always return exactly -1 or 1.

Integer already has a natural ordering by numeric value. Therefore:

~~~java
PriorityQueue<Integer> numbers = new PriorityQueue<>();
~~~

creates a queue that can pick the smallest number as its head without passing a custom rule. This is an illustrative declaration using `java.util.PriorityQueue`.

After inserting `6, 2, 9, 1, 5`:

~~~text
peek()           → 1, without removing
consecutive poll → 1, 2, 5, 6, 9
~~~

Natural ordering does not mean "the order in which data appears" or "automatically ascending across all fields". For a custom type, the type's author must define the ordering via Comparable if they want to provide a natural ordering. [Java 17: Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html).

A record does not automatically get `compareTo` just because it has numeric fields, `equals`, or `toString`. When a type lacks a suitable natural ordering, an external Comparator can be supplied.

## 3. Comparator Describes the Queue's Own Priority Rule

`Comparator<T>` has the main method:

~~~java
int compare(T left, T right);
~~~

This is a simplified signature for reading its meaning. The rule resides in an external comparator object rather than inside the element class.

With `rule.compare(a, b)`:

~~~text
negative → a must be ordered before b according to rule
0        → rule does not distinguish the level of a and b
positive → a must be ordered after b according to rule
~~~

When a non-null Comparator is passed to the PriorityQueue constructor, that rule alone determines the smallest element and the head of the queue. There is no automatic fallback to natural ordering as a tie-breaker if the Comparator returns 0.

Because of this, the same data can have multiple queues serving different goals:

| Need | Rule to express |
| --- | --- |
| Retrieve the smallest number | Ascending natural ordering |
| Retrieve the largest number | Reverse of natural ordering |
| Jobs with higher urgency go first | Compare urgency in descending order |
| With equal urgency, the job that arrived first goes first | Chain arrival sequence number in ascending order |

You do not need to force a class to implement multiple different natural orderings for different screens or workflows. Use-case-specific rules can be kept in separate Comparators.

## 4. Putting the Largest Number at the Head: Reversing the Comparison Rule

Example:

~~~java
PriorityQueue<Integer> largestFirst =
        new PriorityQueue<>(Comparator.reverseOrder());
~~~

With the same input `6, 2, 9, 1, 5`:

~~~text
peek()           → 9
consecutive poll → 9, 6, 5, 2, 1
~~~

Under the reversed comparator, 9 comes before 6, so 9 is the smallest element **in the relation defined by the comparator**. This is not PriorityQueue switching to a "poll from the tail" API.

The operations remain the same: `offer`/`add` inserts, `peek` inspects the head, `poll` retrieves and removes the head. You change the priority rule when constructing the object, not `poll` into a different method.

The `comparator()` method returns the explicit comparator, or null when natural ordering is used. Therefore:

~~~text
queue.comparator() == null
~~~

does not mean "the queue has no ordering". It indicates that no separate Comparator object is being used.

Nor should you infer from a null comparator that the queue allows null elements. Those are two separate questions.

## 5. Translating Business Rules into a Comparator

In this lesson, each job has three components:

~~~text
id       : name to identify the job in the example
urgency  : urgency level; larger numbers need to be processed first
sequence : sequence number when the job is submitted; smaller numbers arrive first
~~~

The model:

~~~java
record Job(String id, int urgency, long sequence) {}
~~~

is a simple value type. It does not implement Comparable. The components used for the rule remain stable after the object is created.

To process high urgency first, then by arrival order within the same level, use:

~~~java
Comparator<Job> executionOrder =
        Comparator.comparingInt(Job::urgency).reversed()
                .thenComparingLong(Job::sequence);
~~~

This is the rule used in the complete program.

How to read each part:

1. `Job::urgency` extracts the job's urgency level.
2. `comparingInt` creates an integer comparison rule by urgency.
3. `reversed` reverses only the urgency criterion so larger numbers come first.
4. `thenComparingLong` uses the sequence number only when urgency levels are equal.

The queue is created with:

~~~java
PriorityQueue<Job> scheduled = new PriorityQueue<>(executionOrder);
~~~

The fact that Job does not have `compareTo` causes no issue when a Comparator provides a valid comparison for the elements. Conversely, if you omit the comparator while still using this Job, you have not provided any way for the queue to establish an ordering.

## 6. Equal Priority Only Preserves Arrival Order with a Secondary Key

A Comparator that only reads `urgency` will return 0 for two Jobs at the same level. PriorityQueue still retains both, but makes no promise to process the earlier-added Job first. If the requirement is higher urgency first and earlier-arriving first among ties, compare `urgency` descending and then `sequence` ascending, like `executionOrder` in section 5.

For example, `alert(5,1)` and `backup(5,2)` both come before `report(2,0)`; within level 5, alert comes before backup thanks to sequence. If sequence cannot distinguish two submissions, the comparator still allows a tie. Arrival order and sequence-assignment policies are analyzed in depth in the lesson on tied elements.
## 7. Placing `reversed` in the Wrong Position Changes the Secondary Criterion Too

Compare these two expressions:

~~~java
Comparator<Job> correctForThisExample =
        Comparator.comparingInt(Job::urgency).reversed()
                .thenComparingLong(Job::sequence);
~~~

and:

~~~java
Comparator<Job> differentRule =
        Comparator.comparingInt(Job::urgency)
                .thenComparingLong(Job::sequence)
                .reversed();
~~~

The first expression reverses urgency before chaining sequence. It produces "urgency descending, sequence ascending".

The second expression chains two ascending criteria and then reverses the entire comparator. It produces "urgency descending, sequence descending". Within the same urgency group, the job with the later arrival number is ordered first.

You cannot detect this bug with a sample where every job has a different urgency. Always include at least one pair with equal urgency but different sequence numbers to verify your intent.

Comparator chaining methods describe ordering criterion by criterion. Only when the preceding criterion returns 0 does the next criterion decide. Always check the scope of each `reversed` call, rather than seeing that keyword and assuming "everything is descending priority". [Java 17: Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

## 8. Ties Do Not Cause the Queue to Deduplicate

With `alpha` and `beta` both having `urgency = 3`, comparing by urgency yields 0, yet the two distinct records can both reside in the PriorityQueue. Adding the same element again also creates another occurrence; the queue has no deduplication contract.

`contains(Object)` and `remove(Object)` search for an element using `equals`, not by matching any Job with the same priority level. The program in section 10 verifies the comparison result, equality check, size, and lookup of another Job. Clearly distinguish `remove()` (which removes the priority head) from `remove(Object)` (which removes a matching value).
## 9. Iteration Order Is Not Poll Order

A heap only maintains parent-child relationships sufficient to know the head element. `iterator()`, for-each, `toArray()`, and printing the queue are not guaranteed to follow priority order. To inspect the processing order, use `poll()` on a copy or sort a list with the appropriate comparator. The lesson on iterators goes deeper into these guarantees and how to test them.
## 10. Complete Program Using Java 17

Save as `PriorityQueueOrderingDemo.java`. The program avoids printing an arbitrary iterator order as a "sorted" result. For tied-priority cases without a secondary criterion, it checks only the count and urgency level, without assuming any name order.

Job has a custom `toString` for concise output in the format `id/urgency/sequence`. Ordering is not determined from this display string; the Comparator reads the corresponding fields.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Queue;

public class PriorityQueueOrderingDemo {
    record Job(String id, int urgency, long sequence) {
        @Override
        public String toString() {
            return id + "/" + urgency + "/" + sequence;
        }
    }

    static <E> List<E> drain(Queue<E> queue) {
        List<E> result = new ArrayList<>();
        E next;
        while ((next = queue.poll()) != null) {
            result.add(next);
        }
        return result;
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(6, 2, 9, 1, 5);
        PriorityQueue<Integer> natural = new PriorityQueue<>();
        natural.addAll(input);
        System.out.println("natural comparator is null=" + (natural.comparator() == null));
        System.out.println("natural peek=" + natural.peek());
        System.out.println("natural size after peek=" + natural.size());
        List<Integer> naturalSnapshot = new ArrayList<>(natural);
        naturalSnapshot.sort(natural.comparator());
        System.out.println("natural sorted snapshot=" + naturalSnapshot);
        System.out.println("natural copy drain=" + drain(new PriorityQueue<>(natural)));
        System.out.println("natural original size=" + natural.size());
        System.out.println("natural original poll=" + natural.poll());
        System.out.println("natural original size after poll=" + natural.size());

        PriorityQueue<Integer> reverse =
                new PriorityQueue<>(Comparator.reverseOrder());
        reverse.addAll(input);
        System.out.println("reverse comparator is null=" + (reverse.comparator() == null));
        System.out.println("reverse peek=" + reverse.peek());
        List<Integer> reverseSnapshot = new ArrayList<>(reverse);
        reverseSnapshot.sort(reverse.comparator());
        System.out.println("reverse sorted snapshot=" + reverseSnapshot);
        System.out.println("reverse drain=" + drain(reverse));
        System.out.println("reverse empty peek=" + reverse.peek());
        System.out.println("reverse empty poll=" + reverse.poll());

        Job alpha = new Job("alpha", 3, 0);
        Job beta = new Job("beta", 3, 1);
        Comparator<Job> urgencyOnly = Comparator.comparingInt(Job::urgency);
        PriorityQueue<Job> ties = new PriorityQueue<>(urgencyOnly);
        ties.offer(alpha);
        ties.offer(beta);
        System.out.println("tied comparison=" + urgencyOnly.compare(alpha, beta));
        System.out.println("tied equals=" + alpha.equals(beta));
        System.out.println("tied size=" + ties.size());
        Job probe = new Job("unknown", 3, 99);
        System.out.println("contains equal-priority probe=" + ties.contains(probe));
        System.out.println("remove equal-priority probe=" + ties.remove(probe));
        System.out.println("offer same job again=" + ties.offer(alpha));
        System.out.println("size with repeated job=" + ties.size());
        List<Job> tiedResults = drain(ties);
        System.out.println("tied drain count=" + tiedResults.size());
        System.out.println("all tied urgency=3="
                + tiedResults.stream().allMatch(job -> job.urgency() == 3));

        List<Job> jobs = List.of(
                new Job("report", 2, 0),
                new Job("alert", 5, 1),
                new Job("backup", 5, 2),
                new Job("cleanup", 1, 3));
        Comparator<Job> executionOrder =
                Comparator.comparingInt(Job::urgency).reversed()
                        .thenComparingLong(Job::sequence);
        PriorityQueue<Job> scheduled = new PriorityQueue<>(executionOrder);
        scheduled.addAll(jobs);
        System.out.println("scheduled peek=" + scheduled.peek());
        List<Job> scheduledSnapshot = new ArrayList<>(scheduled);
        scheduledSnapshot.sort(scheduled.comparator());
        System.out.println("scheduled sorted snapshot=" + scheduledSnapshot);
        System.out.println("scheduled copy drain="
                + drain(new PriorityQueue<>(scheduled)));
        System.out.println("scheduled original size=" + scheduled.size());

        PriorityQueue<Job> noRule = new PriorityQueue<>();
        try {
            noRule.offer(new Job("missing", 1, 0));
        } catch (ClassCastException exception) {
            System.out.println("missing natural ordering="
                    + exception.getClass().getSimpleName());
        }

        PriorityQueue<Integer> nullFriendlyRule =
                new PriorityQueue<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        try {
            nullFriendlyRule.offer(null);
        } catch (NullPointerException exception) {
            System.out.println("null despite comparator="
                    + exception.getClass().getSimpleName());
        }
        System.out.println("null queue size=" + nullFriendlyRule.size());

        Comparator<Integer> unsafe = (left, right) -> left - right;
        System.out.println("unsafe edge sign="
                + Integer.signum(unsafe.compare(Integer.MIN_VALUE, Integer.MAX_VALUE)));
        System.out.println("safe edge sign="
                + Integer.signum(Integer.compare(Integer.MIN_VALUE, Integer.MAX_VALUE)));
    }
}
~~~

Compile and run in the directory containing the file:

~~~shell
javac --release 17 -encoding UTF-8 PriorityQueueOrderingDemo.java
java PriorityQueueOrderingDemo
~~~

Use JDK 17 or later. `--release 17` checks code and APIs against Java 17; the filename matches the public class.

Expected output:

~~~text
natural comparator is null=true
natural peek=1
natural size after peek=5
natural sorted snapshot=[1, 2, 5, 6, 9]
natural copy drain=[1, 2, 5, 6, 9]
natural original size=5
natural original poll=1
natural original size after poll=4
reverse comparator is null=false
reverse peek=9
reverse sorted snapshot=[9, 6, 5, 2, 1]
reverse drain=[9, 6, 5, 2, 1]
reverse empty peek=null
reverse empty poll=null
tied comparison=0
tied equals=false
tied size=2
contains equal-priority probe=false
remove equal-priority probe=false
offer same job again=true
size with repeated job=3
tied drain count=3
all tied urgency=3=true
scheduled peek=alert/5/1
scheduled sorted snapshot=[alert/5/1, backup/5/2, report/2/0, cleanup/1/3]
scheduled copy drain=[alert/5/1, backup/5/2, report/2/0, cleanup/1/3]
scheduled original size=4
missing natural ordering=ClassCastException
null despite comparator=NullPointerException
null queue size=0
unsafe edge sign=1
safe edge sign=-1
~~~

## 11. Reading the Evidence from the Program

### 11.1. Natural: Smallest Number at the Head

`natural peek=1` together with `natural size after peek=5` confirms that inspecting the head does not remove it.

Both the sorted snapshot and the drained copy produce `[1, 2, 5, 6, 9]`. `natural original size=5` shows that draining a copy does not empty the original queue.

After actually calling `poll` on the original queue, the result is 1 and the original size drops to 4. That is a mutating operation, unlike `peek`.

### 11.2. Reversed: Largest Number at the Head

`reverse peek=9` and `reverse drain=[9, 6, 5, 2, 1]` confirm that the reversed rule changed the retrieval order.

The `reverse` queue is drained directly by `drain`. Therefore, the two subsequent peek/poll calls return null because it is empty. No default element is fabricated when data runs out.

### 11.3. Ties Are Not Dropped

`tied size=2` and `size with repeated job=3` show that the queue retains both distinct values at the same level and a re-insertion of `alpha` itself.

The outputs `tied drain count=3` and `all tied urgency=3=true` verify what the contract allows us to assert. The program does not print a name order for this group, because the Comparator has not defined a criterion to distinguish elements at level 3.

### 11.4. Secondary Criterion Produces the Desired Order

`scheduled peek=alert/5/1` is the head under "urgency descending, then sequence ascending".

Both the sorted snapshot and the drained copy produce:

~~~text
alert/5/1, backup/5/2, report/2/0, cleanup/1/3
~~~

Alert comes before backup because both have urgency 5, but alert has a smaller sequence. Report does not move ahead simply because it arrived earlier; urgency is the primary criterion.

`scheduled original size=4` shows that creating a snapshot and draining a copy do not remove data from the original queue.

## 12. Viewing the Order Without Emptying the Queue

There are two approaches in the program, each suited for verification.

**First approach: take a snapshot into a list and sort it.**

~~~java
List<Job> snapshot = new ArrayList<>(scheduled);
snapshot.sort(scheduled.comparator());
~~~

The initial list is not yet considered to be in priority order. Calling `sort` applies the original queue's rule to the snapshot. Reordering the list does not alter the elements in the queue.

For the natural-ordering integer example, `comparator()` returns null. `List.sort(null)` is defined to use natural ordering, so the same pattern still works for elements with a valid natural ordering. [Java 17: List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

**Second approach: create a new PriorityQueue from the original PriorityQueue and poll the copy.**

~~~java
PriorityQueue<Job> copy = new PriorityQueue<>(scheduled);
List<Job> ordered = drain(copy);
~~~

Constructing from a PriorityQueue preserves the original's ordering rule. The copy has an independent internal structure, so `drain(copy)` does not remove elements from `scheduled`.

Both approaches perform a shallow copy of the elements: the new list or queue can still hold references to the same Job objects. In this lesson, Job is a record value with stable priority fields, so no element mutation interferes.

If the Comparator does not distinguish tied elements, a sorted list may preserve one order among them based on the snapshot's input order, while polling a copy may pick differently within the tied group. Do not treat a single matching run as a stability guarantee of PriorityQueue.

## 13. A Comparator Must Obey the Ordering Contract

A well-behaved rule must be consistent across comparisons:

- Reversing the two arguments must negate the sign of the result.
- The before/after relation must be transitive.
- When two elements compare equal to 0, they must have the same sign relationship with any third element.

The rule must hold for all elements the queue is allowed to accept, not just a single sample pair.

Do not compare integers by subtraction if overflow is possible:

~~~java
Comparator<Integer> unsafe = (left, right) -> left - right;
~~~

This is a bug illustration and must not be used to construct a queue in production code.

With `Integer.MIN_VALUE` and `Integer.MAX_VALUE`, subtraction can overflow and produce the opposite sign of what was intended. The program prints:

~~~text
unsafe edge sign=1
safe edge sign=-1
~~~

Use `Integer.compare` or `comparingInt` helpers to express integer comparisons instead of relying on subtraction. When reversing direction, use `reversed` or compare arguments in the intended direction.

Do not return 1 just to prevent two distinct elements from being treated as "duplicates". PriorityQueue does not need that trick to keep multiple elements at the same level, and a Comparator that violates the contract can cause head selection to behave incorrectly.

## 14. Comparison Keys Must Remain Stable While in the Queue

Directly mutating `urgency` on an object already inside the queue or changing external state read by the comparator does not automatically trigger sift-up/sift-down. `peek()` may continue returning the head according to the old layout. The example's `Job` record keeps its comparison fields stable; if you need to change priority, perform a controlled removal of the old entry followed by inserting the new value, while accounting for duplicate elements and lookup cost.

The lesson on changing priority explains additional ways to restore the heap and constraints during continuous updates.
## 15. Missing Natural Ordering and Disallowing null

Two distinct errors are verified at the end of the program.

**No comparison rule for Job.**

~~~java
PriorityQueue<Job> noRule = new PriorityQueue<>();
~~~

Job in this lesson does not implement Comparable. Without passing a Comparator, inserting a Job leads to `ClassCastException` in the example.

The declaration `PriorityQueue<Job>` still compiles because PriorityQueue must support non-Comparable types when an external comparator is provided. Generics do not automatically generate `compareTo` for Job.

**A Comparator that accepts null does not make PriorityQueue accept null.**

The program creates a comparator wrapped with `nullsFirst` and still receives `NullPointerException` on `offer(null)`. PriorityQueue forbids null elements by the class's own contract, before the priority rule can ever be used to store it.

Do not reason that "my Comparator handles null, so every structure accepting it can store null". Element policies belong to the receiving collection as well, not just the comparison function.

When a valid queue is empty, `peek` and `poll` use null as the result indicating no element is available. That is a different role from attempting to insert null as data.

## 16. Limitations to Keep in Mind When Choosing PriorityQueue

PriorityQueue is suitable when you need to continuously add elements and retrieve the head according to a priority order. It does not automatically provide a fully sorted list for every traversal.

The API documents `O(log n)` time for insertion/removal operations such as `offer`, `add`, `poll`, and no-arg `remove`; `peek`, `element`, and `size` run in constant time. Searching for or removing a specific object via `contains`/`remove(Object)` takes linear time in this implementation.

Do not use a single print or a small benchmark to extrapolate broader guarantees. Those figures describe the `PriorityQueue` class, not every `Queue` available in Java.

The initial capacity is not a fixed limit on how many jobs can be accepted. PriorityQueue grows its internal storage as needed; the specific growth policy is not an API that application code should depend on.

Also, the class is not synchronized for concurrent modification by multiple threads. Choosing the right Comparator does not replace proper data-sharing design. This lesson's program uses a single thread and immutable values so results can be compared directly.

If the goal is only to take a snapshot and display everything in order, a sorted list may express that task more clearly. If unique elements according to some equality definition are needed, an appropriate uniqueness model must be added; PriorityQueue does not deduplicate on its own.

## 17. Common Misconceptions

| Misconception | How to verify correctly |
| --- | --- |
| "High priority means the largest number always comes out first" | Check the Comparator; by default, the smallest Integer is at the head |
| "Poll switches to taking from the tail when using reverseOrder" | Poll still takes the head; the rule defining the head changed |
| "Returning null from comparator() means there is no ordering" | A null `comparator()` indicates natural ordering |
| "A record automatically has compareTo" | It needs an explicit Comparable implementation or Comparator |
| "Equal priority means FIFO" | There is no such guarantee unless an arrival-order criterion is added |
| "When compare returns 0, the new element is dropped" | PriorityQueue can hold multiple elements at the same level and even duplicates |
| "Contains finds any element at the same priority level" | It searches by `equals`, not by priority group |
| "Iterator/toString reflects poll order" | No guarantee; verify with `poll` or by sorting a snapshot |
| "Placing reversed anywhere in the chain is the same" | Reversing at the end of the chain also reverses chained secondary criteria |
| "Subtracting two numbers is a safe comparison" | Can overflow; use `Integer.compare` or standard helpers |
| "Mutating urgency directly updates the queue" | The queue does not automatically track and reposition elements |
| "NullsFirst allows inserting null into PriorityQueue" | The class still forbids null |
| "Copying the queue creates completely new element objects" | Copying the structure does not deep-clone Job |
| "Initial capacity is the maximum number of jobs" | That is not a fixed limit of PriorityQueue |

The most important test sample should include an early-arriving element with low priority, two elements with equal priority, and boundary numeric values. Those three groups help catch FIFO assumptions, missing tie-breakers, and subtraction-based comparison bugs.

## 18. Practice with Solutions

### Exercise 1: Natural Ordering

Insert `8, 3, 6, 1` into a default `PriorityQueue<Integer>`. What does `peek` return? In what order does `poll` drain them?

**Solution:** `peek` returns 1 without removing it. Consecutive `poll` calls yield `1, 3, 6, 8`. The fact that 8 arrived first does not give it higher priority.

### Exercise 2: Reversing the Rule

Use the same data with `Comparator.reverseOrder`. What are the head and the drain order?

**Solution:** The head is 8. `poll` yields `8, 6, 3, 1`. The reversed rule puts larger numbers first, while `poll` still removes from the head.

### Exercise 3: Business Priority

Job A has urgency 2, sequence 0; Job B has urgency 5, sequence 1. Under `executionOrder` in the lesson, which comes out first?

**Solution:** B comes out first because urgency is the primary criterion in descending order. A's earlier sequence only matters when urgency levels are equal.

### Exercise 4: Ties

A and B both have urgency 4, and A arrives before B. The Comparator only checks urgency. Can you assert in a test that A is guaranteed to be polled first?

**Solution:** Not under the PriorityQueue contract. To guarantee arrival order, add a corresponding criterion such as an ascending sequence assigned properly on each insertion.

### Exercise 5: Reversing the Whole Chain

You chain urgency ascending then sequence ascending, and finally call `reversed` on the whole comparator. Among jobs with equal urgency, does the smaller or larger sequence come first?

**Solution:** The larger sequence comes first because the entire rule was reversed. That differs from reversing only urgency and then chaining sequence ascending.

### Exercise 6: Elements with Equal Priority

Two Jobs are not equal according to `equals`, but the Comparator returns 0. Does adding both to a PriorityQueue force it to keep only one?

**Solution:** No. Both can be kept. PriorityQueue does not use a 0 comparison result to exclude elements like a sorted set does.

### Exercise 7: Searching with an Equal-Priority Probe

The queue contains `alpha` with urgency 3. A probe has a different id and sequence, but also urgency 3. Does `contains(probe)` return true just because of the same priority?

**Solution:** No. `contains` uses `equals`. The `Job` record compares its components, so a probe differing in those values is not considered the same element just because urgency matches.

### Exercise 8: Displaying in Priority Order While Preserving the Source

You need to print all Jobs in `executionOrder` without emptying `scheduled`. What are the two ways shown in the lesson?

**Solution:** Snapshot into an `ArrayList` and sort using `scheduled`'s comparator; or create a copy `PriorityQueue` preserving the same rule and `poll` the copy. Relying only on the source's `iterator` or `toString` does not guarantee priority order.

### Exercise 9: Job Without Comparable

A `Job` record that does not implement `Comparable` is inserted into a `PriorityQueue` with no `Comparator` passed. Does the fact that the generic type compiles prove the queue can be used?

**Solution:** No. You must still provide a natural ordering or a valid Comparator. The program demonstrates `ClassCastException` when both natural ordering and a custom comparator are missing.

### Exercise 10: null

A Comparator is wrapped with `nullsFirst`. Is `offer(null)` into PriorityQueue allowed?

**Solution:** No. PriorityQueue forbids null by its class contract. A Comparator's ability to handle null does not change that.

### Exercise 11: Changing Urgency

An object currently in the queue is assigned a new urgency. Can you assume `peek` afterward automatically reflects the new position?

**Solution:** No. The queue does not automatically track internal assignments. Use immutable data and an explicitly designed priority-update operation.

### Exercise 12: Boundary Values

Why can a `Comparator<Integer>` written as `left - right` pick the wrong head for very small and very large numbers?

**Solution:** `int` subtraction can overflow, flipping the sign of the result. `Integer.compare` or standard comparison helpers express the ordering without subtracting like that.

## 19. Self-Check When Writing a New Rule

Before creating a PriorityQueue, state in words which element must come out first and why. Translate that answer into individual criteria, determine the direction of each criterion, and decide how ties are resolved.

Next, verify with actual `poll` order on a meaningful sample. If you need to preserve the source queue, use a sorted snapshot or a copy with the same rule.

Finally, keep three concerns separate: priority order, element identity via `equals`, and data stability while stored. A correct Comparator selects the head; it does not automatically provide deduplication, implicit updates, or FIFO for cases the rule has not distinguished.
