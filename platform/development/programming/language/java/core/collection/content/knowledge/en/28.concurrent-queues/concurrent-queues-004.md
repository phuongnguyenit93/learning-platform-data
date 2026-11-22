# ArrayBlockingQueue vs. LinkedBlockingQueue

## 1. Shared Producer–Consumer Coordination, Different Storage and Internal Coordination

In a multithreaded pipeline, producers create work and place it into a queue; consumers take work out to process it. When the two sides run at different speeds, the queue holds the pending work and provides a place to enforce a policy when no data is available or no space remains.

`ArrayBlockingQueue<E>` and `LinkedBlockingQueue<E>` both fulfill that role through the `BlockingQueue<E>` interface. Both are FIFO queues: elements are added at the tail and removed from the head. Both can be used with multiple producers and multiple consumers.

The key differences come down to three questions:

1. How is capacity chosen and bounded?
2. Are element references stored in an array or in linked nodes?
3. What locking mechanism coordinates insertion and removal operations?

Those differences affect memory allocation, contention, and performance. They do not turn the `put`, `take`, or timeout contracts into a different set of APIs.

Therefore, you should learn them in two layers: understand the shared behavior to write correct pipelines, then understand the trade-offs of each implementation to choose and measure. Do not choose one simply because "arrays are faster" or "two locks are always faster than one lock."

This lesson uses Java 17 or later. The three standalone programs below each include a filename, compile command, and stdout. These programs verify behavior and shared interface usage; they are not performance benchmarks.

## 2. Comparison Table to Identify What to Examine

| Aspect | ArrayBlockingQueue | LinkedBlockingQueue |
|---|---|---|
| Element storage structure | Fixed-size array of references | Linked nodes holding references |
| Capacity at creation | Must specify capacity | Can be specified; defaults to `Integer.MAX_VALUE` |
| Capacity after creation | Does not resize automatically | Chosen bound does not resize automatically either |
| Element ordering | FIFO | FIFO |
| Fairness option via constructor | Has a `fair` flag | No corresponding flag |
| Storage structure allocation | Array pre-allocated to capacity | Nodes allocated as elements are inserted |
| Add/remove coordination in OpenJDK 17 | One main lock, two wait conditions | Separate put lock and take lock, with count coordination |
| Speed conclusion | Must be measured under an appropriate workload | Must be measured under an appropriate workload |

The points about lock structure here describe the OpenJDK 17 implementation; capacity, FIFO ordering, and constructors are what users read from the API contract. See [ArrayBlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html) and [LinkedBlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html).

"Linked" does not mean capacity grows without bound if the application has passed an explicit limit. "Array" also does not mean the application can access internal slots like an indexed list. Both are still used as queues.

In the rest of this lesson, keep these easily conflated properties separate:

- **Capacity:** the maximum number of elements the queue can hold.
- **Current element count:** the state at a single point of observation.
- **Actual memory usage:** includes the queue structure, element data, and any other retained references.
- **Processing capability:** the throughput and latency of the entire pipeline.

A change in one property does not prove the remaining properties will improve.

## 3. Capacity: Constructor Differences Can Change Operational Policy

### 3.1. When Both Specify a Bound, Both Are Bounded Queues

Both of the following constructions choose a maximum of 100 queued elements:

```java
// Illustrative code inside a method, not a standalone program.
BlockingQueue<Job> array = new ArrayBlockingQueue<>(100);
BlockingQueue<Job> linked = new LinkedBlockingQueue<>(100);
```

When full, `put` can wait for space. If you do not want to wait on full/empty conditions, use `offer` or `poll` and handle the result. The timed overloads allow waiting according to the caller's policy.

Capacity must be positive when using the capacity-taking constructors of these two classes. Do not choose a capacity of 0 to represent an unbuffered handoff mechanism; that is a different requirement from the two structures being compared here.

### 3.2. Default LinkedBlockingQueue Does Not Create a Small, Useful Bound

The no-argument constructor of `LinkedBlockingQueue` uses `Integer.MAX_VALUE`. That number is not a guarantee that enough memory exists to hold over two billion jobs. Resources can be exhausted long before that.

If you replace a queue of capacity 100 with `new LinkedBlockingQueue<>()`, the application has changed the job acceptance limit, not just the storage layout. Producers can keep submitting while consumers are slow, increasing the number of queued jobs and wait times.

Therefore, before discussing memory or speed, check which constructor is actually being called.

### 3.3. Program Comparing Capacity and Ordering

File `QueueCapacityComparisonDemo.java`:

```java
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

public class QueueCapacityComparisonDemo {
    static void inspect(String label, BlockingQueue<Integer> queue) {
        boolean first = queue.offer(10);
        boolean second = queue.offer(20);
        boolean third = queue.offer(30);
        System.out.println(label + ": offers=" + first + "," + second + "," + third
                + "; remaining=" + queue.remainingCapacity());
        System.out.println(label + ": poll=" + queue.poll() + ","
                + queue.poll() + "," + queue.poll());
    }

    public static void main(String[] args) {
        inspect("array-2", new ArrayBlockingQueue<>(2));
        inspect("linked-2", new LinkedBlockingQueue<>(2));

        var defaultLinked = new LinkedBlockingQueue<Integer>();
        System.out.println("defaultLinkedInitial=" +
                defaultLinked.remainingCapacity());
        defaultLinked.offer(99);
        System.out.println("defaultLinkedAfterOne=" +
                defaultLinked.remainingCapacity());

        List<Integer> seed = List.of(10, 20);
        var seededArray = new ArrayBlockingQueue<Integer>(2, false, seed);
        var seededLinked = new LinkedBlockingQueue<Integer>(seed);
        System.out.println("seededArrayRemaining=" +
                seededArray.remainingCapacity());
        System.out.println("seededLinkedRemaining=" +
                seededLinked.remainingCapacity());
        System.out.println("seededArrayOffer30=" + seededArray.offer(30));
        System.out.println("seededLinkedOffer30=" + seededLinked.offer(30));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 QueueCapacityComparisonDemo.java
java QueueCapacityComparisonDemo
```

Stdout:

```text
array-2: offers=true,true,false; remaining=0
array-2: poll=10,20,null
linked-2: offers=true,true,false; remaining=0
linked-2: poll=10,20,null
defaultLinkedInitial=2147483647
defaultLinkedAfterOne=2147483646
seededArrayRemaining=0
seededLinkedRemaining=2147483645
seededArrayOffer30=false
seededLinkedOffer30=true
```

The first two `inspect` calls both use capacity 2. Both accept 10 and 20, reject 30 with `false`, and then retrieve 10 and 20 in FIFO order. After two removals, the third `poll` returns `null`.

The `defaultLinked` section adds only a single element. The program does not attempt to fill the default bound. The large numbers printed are the remaining count limit per the API, not the amount of usable memory remaining.

### 3.4. Collection Constructor Does Not Use size as capacity

An easy replacement mistake to overlook is assuming that initializing `LinkedBlockingQueue` from a two-element collection creates a capacity of 2. In reality, that constructor also uses the `Integer.MAX_VALUE` bound and then loads the initial contents.

In the program:

- `seededArray` is given an explicit capacity of 2 and filled with two elements, so it does not accept 30 via `offer`.
- `seededLinked` receives the same initial collection, but its bound is not 2, so it accepts 30.

To preserve the desired bound when initializing data for a linked queue, you can create it with the capacity constructor and then load the data using an appropriate workflow. Loading must also check the element count and the policy when full.

Do not swap constructors during a class change while overlooking this difference; this can be a more significant behavioral change than any performance difference.

## 4. Circular Array and Linked Nodes: Understanding Memory Cost Accurately

### 4.1. ArrayBlockingQueue Holds an Array of References

Conceptual model of the array queue:

```text
Slots of a pre-allocated array
    [ reference ][ reference ][ empty slot ][ empty slot ]

The take index and put index move through the array.
When reaching the end, they wrap around to the beginning to reuse empty slots.
```

This is an array holding references to objects, not a region pre-allocated with all job objects. Creating a queue of capacity 1,000 does not create 1,000 `Job` objects.

Slots are reused as elements are removed. The normal add/remove path does not need to create a new linked node for each element. However, do not turn that into "every call allocates nothing": the application may still create jobs, use iterators, or call operations that return copies of data.

When choosing a very large capacity, the pre-allocated reference array is also an upfront memory cost you must accept, even when the queue is mostly empty.

### 4.2. LinkedBlockingQueue Holds a Chain of Nodes

Conceptual model of the linked queue:

```text
Head → [ node: reference A ] → [ node: reference B ] → Tail

Each node carries a link to the next node.
Objects A and B remain separate data outside the nodes.
```

In OpenJDK 17, a node contains an element field and a field linking to the next node. Capacity is a count limit; no reference array of length equal to that limit is pre-allocated. Nodes are allocated along the insertion path. See [the OpenJDK 17 LinkedBlockingQueue implementation](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/concurrent/LinkedBlockingQueue.java).

This creates a trade-off to measure: you do not pay upfront for an array sized to capacity, but you incur additional node objects and allocation/reclamation activity during use.

Do not assign a fixed byte count per node across all JVMs. Object size, alignment, and reference representation depend on the virtual machine configuration.

### 4.3. Comparing Mostly Empty vs. Nearly Full Structures Are Two Different Scenarios

If the chosen capacity is very large while occupancy is usually small, the pre-allocated array can be significant. If the queue continuously holds many elements or turns over very rapidly, the node overhead and garbage collection cost of the linked approach need to be examined.

Those are reasoning scenarios for forming measurement hypotheses, not a conclusion that one side always uses less memory in every state.

You must also account for the data held by each element. A job carrying an image, a large buffer, or an object graph can account for most of the memory, far exceeding the cost of a reference slot or a queue node.

An empty array slot creates no work, whereas a reference inside the queue can keep large data alive longer than intended.

### 4.4. Capacity Is Not Yet a Bound on the Pipeline's Total Memory

Capacity limits the number of elements currently queued. It does not limit the number of blocked threads, the objects producers have already created before submitting, or jobs consumers have already taken out but not yet finished processing.

Reasoning example: a queue has capacity 100, but thousands of producer tasks each create a large job and then call `put`. The jobs sitting outside the queue that those tasks still hold also consume memory.

Similarly, multiple consumers can simultaneously hold in-flight jobs. Observing `queue.size()` alone does not tell you the total number of unfinished jobs.

When setting goals to bound memory or active job counts, define the full boundary of the pipeline. Neither queue automatically manages objects outside its own queued elements.

## 5. One Lock vs. Two Locks: Differences Create Opportunity, Not Speed Guarantees

### 5.1. ArrayBlockingQueue Coordinates Through One Main Lock

In OpenJDK 17, `ArrayBlockingQueue` guards the array state, count, and put/take indices with a single main `ReentrantLock`. It has two conditions, `notEmpty` and `notFull`, to wait for data or wait for space. See [the OpenJDK 17 ArrayBlockingQueue implementation](https://raw.githubusercontent.com/openjdk/jdk17u/master/src/java.base/share/classes/java/util/concurrent/ArrayBlockingQueue.java).

Model to visualize:

```text
Put  → main lock → update array/count → release lock
Take → main lock → update array/count → release lock

Empty/full → wait on the appropriate condition
```

One main lock does not mean a `take` thread waiting on empty holds the lock forever and prevents producers from entering. Condition waiting must allow the other side to change the condition.

Nor does it mean all of the user's job processing runs inside the queue lock. After `take` returns an element, the application's own processing code is not automatically wrapped inside that internal lock region.

### 5.2. LinkedBlockingQueue Separates the Put Path and Take Path

In the OpenJDK 17 implementation, `LinkedBlockingQueue` has separate locks for the put side and take side, along with an atomic count for coordination. Some operations need to coordinate both sides. This is an implementation detail that helps explain the potential to overlap certain activities, not a locking API for applications to rely on.

```text
Put  → put lock  → update tail
                    ↕ coordinate count and signals
Take → take lock → update head
```

Producers can still contend on the same put lock. Consumers can still contend on the same take lock. The two sides are also not completely independent because they must share state and wake the appropriate waiting side.

Therefore, two locks do not mean every `put` and `take` always run in parallel, nor do they mean throughput must double. Operations such as arbitrary removal, producing certain observed views, or bulk processing can have coordination paths different from head/tail put/take.

### 5.3. Neither Class Becomes Lock-Free Just Because of the Concurrent Name

Both classes being compared are blocking queues. Using `offer(e)` to avoid waiting for space does not automatically turn the internal execution path into a lock-free algorithm.

Observed speed is also affected by scheduling, number of active threads, queue occupancy, thread wakeups, and allocation. Structural details help form hypotheses, but do not replace measurement.

If you switch classes and speed changes, look for the cause under the same capacity configuration and the same workload model, rather than immediately attributing the result to the number of locks.

## 6. FIFO and Fairness Are Two Separate Concepts

FIFO refers to the ordering of elements in the queue: an element inserted earlier stands ahead of an element inserted later according to the insertion order established by the queue.

Fairness refers to the policy for granting access to waiting threads competing for operations. `ArrayBlockingQueue` has a constructor with a `fair` flag; by default, fairness is not enabled. `LinkedBlockingQueue` has no constructor with a corresponding flag.

Illustrative constructions, not a standalone program:

```java
BlockingQueue<Job> normal = new ArrayBlockingQueue<>(100);
BlockingQueue<Job> fair = new ArrayBlockingQueue<>(100, true);
BlockingQueue<Job> linked = new LinkedBlockingQueue<>(100);
```

The fairness flag does not change the FIFO order of elements into a different order. Nor does it guarantee the completion order of jobs across multiple consumers.

Reasoning example:

```text
Consumer A takes job 1 → takes a long time to process
Consumer B takes job 2 → processes quickly → finishes first
```

There is no contradiction with FIFO: take order and processing completion order are two different things.

The `ArrayBlockingQueue` documentation notes that fairness generally decreases throughput but reduces variability and avoids starvation for some waiting threads. Do not treat it as a guarantee of maximum wait time in milliseconds or immediate CPU scheduling.

To evaluate this flag, observe the distribution of wait times across participants, not just total elements per second. A single run with a few threads printing before/after or calling `Thread.sleep` does not prove the entire fairness policy.

When switching from an `ArrayBlockingQueue` with fairness enabled to `LinkedBlockingQueue`, record this as a change in comparison conditions. Do not silently assume both configurations have the same waiting policy.

## 7. Preserving Waiting Policy When Switching Implementations

### 7.1. The Shared API Preserves Behavior Callers Rely On

Given the same bound and state:

- `put(e)` can wait for space; `take()` can wait for data.
- `offer(e)` reports failure to insert with `false`.
- `poll()` reports no element available with `null`.
- Timed overloads allow waiting for a duration in the chosen unit.
- Blocking operations can throw `InterruptedException`.
- Neither class accepts `null` elements.

This is the contract through `BlockingQueue`, not a difference used to pick one over the other. See [BlockingQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

File `QueueWaitingPolicyDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public class QueueWaitingPolicyDemo {
    static void inspect(String label, BlockingQueue<String> queue)
            throws InterruptedException {
        queue.put("A");
        boolean accepted = queue.offer("B", 20, TimeUnit.MILLISECONDS);
        String first = queue.take();
        String missing = queue.poll(20, TimeUnit.MILLISECONDS);

        System.out.println(label + ": fullOffer=" + accepted
                + "; taken=" + first + "; emptyPoll=" + missing);
        System.out.println(label + ": immediateOffer=" + queue.offer("C")
                + "; next=" + queue.take()
                + "; remaining=" + queue.remainingCapacity());
    }

    public static void main(String[] args) throws InterruptedException {
        inspect("array-1", new ArrayBlockingQueue<>(1));
        inspect("linked-1", new LinkedBlockingQueue<>(1));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 QueueWaitingPolicyDemo.java
java QueueWaitingPolicyDemo
```

Stdout:

```text
array-1: fullOffer=false; taken=A; emptyPoll=null
array-1: immediateOffer=true; next=C; remaining=1
linked-1: fullOffer=false; taken=A; emptyPoll=null
linked-1: immediateOffer=true; next=C; remaining=1
```

Each queue has capacity 1. While holding A and with no consumer taking, a timed attempt to insert B fails with `false`. After A is taken and with no producer inserting, a timed `poll` returns `null`.

When space is available, C is inserted and taken normally. The identical output shows that code using the interface can preserve the call-site policy when switching implementations.

The program does not print actual elapsed time. The 20-millisecond timeout is a parameter allowing a wait, not a stdout expectation about scheduler precision.

### 7.2. Things the Caller Still Must Handle

Switching from array to linked does not fix the following bugs:

- Ignoring `false` from `offer` and assuming the job was accepted.
- Swallowing `InterruptedException` and continuing to wait indefinitely.
- Checking `remainingCapacity()` first and assuming a slot is reserved.
- Checking `isEmpty()` and concluding the source has no more work.
- Holding an external lock while waiting on `put`, when the consumer needs that same lock.
- Submitting both waiting producers and unstarted consumers into an executor pool with no free threads left.

These bugs belong to coordination relationships and task lifecycles. Changing how elements are stored does not break an application-level dependency cycle.

### 7.3. Object Sharing and Source Termination Also Keep the Same Boundaries

Both pass references through the queue. Visibility guarantees at the handoff point do not automatically make mutable sub-data safe for shared use.

If a producer continues modifying a job after submitting it while a consumer reads it concurrently, the application needs an ownership convention, immutable data, or separate synchronization.

Neither class has a built-in queue close command to automatically terminate sources. Stop signals or interruption must be part of an explicit protocol. A timed `poll` expiring is not proof that all producers have finished.

Do not alter data-handling and termination rules just because you changed a constructor.

## 8. The Same Pipeline for Both Classes

### 8.1. Two Producers, Two Consumers

The following program sets the same capacity of 4 for both classes. Two producers submit IDs 1 to 20 and 21 to 40. Two consumers both take data.

The number 0 is reserved as a stop signal; real data in this example is always positive. The main thread sends two signals only after both producers have finished, corresponding to one signal per consumer.

File `CommonQueuePipelineDemo.java`:

```java
import java.util.HashSet;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public class CommonQueuePipelineDemo {
    record Result(int received, int unique, int sum, boolean allIds, int remaining) {}

    static int consume(BlockingQueue<Integer> queue,
            ConcurrentLinkedQueue<Integer> received, CyclicBarrier start)
            throws Exception {
        start.await(10, TimeUnit.SECONDS);
        int sum = 0;
        while (true) {
            int value = queue.take();
            if (value == 0) {
                return sum;
            }
            received.add(value);
            sum += value;
        }
    }

    static Void produce(BlockingQueue<Integer> queue, int from, int to,
            CyclicBarrier start) throws Exception {
        start.await(10, TimeUnit.SECONDS);
        for (int id = from; id <= to; id++) {
            queue.put(id);
        }
        return null;
    }

    static Result run(BlockingQueue<Integer> queue) throws Exception {
        var received = new ConcurrentLinkedQueue<Integer>();
        var start = new CyclicBarrier(4);
        var pool = Executors.newFixedThreadPool(4);

        try {
            var firstConsumer = pool.submit(() -> consume(queue, received, start));
            var secondConsumer = pool.submit(() -> consume(queue, received, start));
            var firstProducer = pool.submit(() -> produce(queue, 1, 20, start));
            var secondProducer = pool.submit(() -> produce(queue, 21, 40, start));

            firstProducer.get(10, TimeUnit.SECONDS);
            secondProducer.get(10, TimeUnit.SECONDS);
            queue.put(0);
            queue.put(0);

            int sum = firstConsumer.get(10, TimeUnit.SECONDS)
                    + secondConsumer.get(10, TimeUnit.SECONDS);
            var unique = new HashSet<>(received);
            boolean allIds = true;
            for (int id = 1; id <= 40; id++) {
                allIds &= unique.contains(id);
            }
            return new Result(received.size(), unique.size(), sum,
                    allIds, queue.size());
        } finally {
            pool.shutdownNow();
        }
    }

    static void print(String label, Result result) {
        System.out.println(label + ": received=" + result.received()
                + "; unique=" + result.unique()
                + "; sum=" + result.sum()
                + "; allIds=" + result.allIds()
                + "; remaining=" + result.remaining());
    }

    public static void main(String[] args) throws Exception {
        print("array-4", run(new ArrayBlockingQueue<>(4)));
        print("linked-4", run(new LinkedBlockingQueue<>(4)));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CommonQueuePipelineDemo.java
java CommonQueuePipelineDemo
```

Stdout:

```text
array-4: received=40; unique=40; sum=820; allIds=true; remaining=0
linked-4: received=40; unique=40; sum=820; allIds=true; remaining=0
```

Four tasks have four execution threads, all passing through a start gate. Consumers can run while producers are waiting for space. The program does not put all threads into blocked producer states and then expect a consumer task in the same pool to start.

The main thread awaits the results of both producers before sending the stop signals. Therefore, no new data from a valid producer in this experiment is placed after those signals.

After all consumers finish, the result is checked against properties that do not depend on work-distribution scheduling:

- All 40 data elements are received.
- There are 40 distinct IDs covering the full range 1 to 40.
- The sum of the IDs is 820.
- No elements remain in the queue.

It does not print which IDs each consumer received, because that split can vary between runs.

### 8.2. What Does This Program Prove and What Does It Not Prove?

It verifies that the same pipeline using `BlockingQueue` runs correctly on both classes with the same bound. It checks for no missing or duplicate IDs in an experiment with defined source conditions.

It does not measure or conclude:

- Which class has higher throughput.
- Which class has lower tail latency.
- The allocation rate of a long-running workload.
- The level of fairness across tasks.
- That every execution schedule of another application is bug-free.

Small integers and simple addition here help keep focus on coordination; they do not represent the size and processing time of all real jobs.

If a consumer fails in a real application, producers can remain blocked in `put`. A complete pipeline also needs error reporting and cancellation so other participants know how to stop. Choosing array or linked does not automatically add that error path.

### 8.3. Do Not Infer Global Order from Multiple Producers' ID Orders

Each producer has its own ascending loop. Because both insert concurrently, the interleaved order does not have to be 1, 2, 3, and so on up to 40.

FIFO applies to the insertion order established at the queue. It does not sort IDs into ascending order, nor does it order by the moment a thread first intended to send data.

If business logic requires ordering by a global sequence number, design the issuance and publication of that number, or choose an appropriate processing mechanism. Do not use FIFO to promise another order that has not been defined.

## 9. Choosing a Class and Measuring Performance Without Changing the Question Midstream

### 9.1. Grounded Selection Directions

| Priority | Direction to Consider |
|---|---|
| Want an explicit mandatory capacity and reuse of a reference array | Consider `ArrayBlockingQueue` |
| Want a fairness option via constructor | Consider `ArrayBlockingQueue` with the appropriate flag |
| Want node structure proportional to data count rather than allocating an array sized to capacity upfront | Consider `LinkedBlockingQueue`, still choosing an intentional bound |
| Have a multithreaded add/take workload needing to test two-sided overlap potential | Measure `LinkedBlockingQueue` under the same workload configuration as the array option |
| Consumers are persistently slower than sources | Revisit processing capacity and full-queue policy; switching classes is not enough |
| Need durability across process restarts or processing acknowledgments | Need mechanisms beyond these two in-memory queues |

These are directions for forming selection hypotheses. No single row in the table is enough to replace real operational requirements.

A pre-allocated array can suit steady workloads and a desire to control memory layout. A linked queue can be a candidate to measure when thread counts and add/take paths make contention a significant factor. Both decisions must still account for element data, bounds, and latency.

### 9.2. Comparisons Must Keep the Same Capacity Policy

A benchmark comparing `new ArrayBlockingQueue<>(100)` against `new LinkedBlockingQueue<>()` may be comparing one side forced to wait against another side continuing to accumulate data.

If you only count how many times producers finish submitting, the result does not tell you which side processes jobs faster or whether acceptable latency is maintained. Unprocessed data may be piling up in memory.

A fair comparison point for the question being asked uses the same capacity, the same full-queue policy, the same number of producers/consumers, and the same work. If you intentionally compare two different policies, state clearly that it is a policy experiment.

The fairness flag of the array option is also a configuration variable that must be recorded.

### 9.3. Metrics to Measure Separately

- **Acceptance throughput:** how many elements are successfully inserted per unit of time.
- **Completion throughput:** how many jobs are completely processed.
- **Insertion wait time:** how long producers are held when full or under contention.
- **Queue residence time:** from when an element is accepted to when it is taken.
- **End-to-end latency:** until processing actually finishes.
- **Memory allocation and reclamation:** queue structure and data must be distinguished.
- **Load state:** number of queued elements, in-flight elements, failed or timed-out submissions.

A benchmark calling `offer` on an always-full queue can report a huge number of calls per second simply because they quickly return `false`. If you ignore the success count, that high number is easily misread as data-processing capacity.

Similarly, a high number of accepted jobs while queue residence time grows unboundedly is a different situation from a pipeline keeping up with load.

### 9.4. Do Not Use a Single Loop and nanoTime to Draw General Conclusions

The JVM needs steady-state execution conditions; results can be affected by JIT compilation, optimizations, allocation, the garbage collector, CPU, and scheduling. Logging on every operation can also make printing cost dominate queue cost.

If microbenchmarking is needed, you can use [OpenJDK's JMH](https://github.com/openjdk/jmh) to structure the measurement, and then combine it with measuring the real application pipeline. Do not take a number from a functional experiment in this lesson as a performance metric.

Workload design should include meaningful states: nearly empty, moderate occupancy, and frequently full; one producer–one consumer and multiple on each side; small jobs and representative payloads.

Keep element creation the same across both options. If one side allocates a new large payload every time while the other reuses a small object, the measurement has changed the data cost too.

### 9.5. Increasing Capacity Does Not Fix a Long-Term Speed Mismatch

Consider a simple model: producers submit 600 jobs per second, consumers only complete the equivalent of 400 jobs per second, rates are treated as steady, and there is no rejection mechanism.

The backlog grows by about 200 jobs per second. Extra space for 1,000 more jobs only absorbs about 5 seconds under this model. This is an estimate to understand the trend, not an exact prediction of execution scheduling or latency for a Java queue.

Switching from array to linked can change coordination cost, but it does not automatically make a slow downstream resource outside the queue process 600 jobs per second. You need to examine the actual bottleneck, scaling processing capacity, throttling sources, and overload policies.

A large queue helps absorb short bursts in some cases, while also holding more data and making jobs wait longer. Capacity is an operational decision, not just an optimization parameter.

## 10. Secondary Operations and Assumptions Not to Carry Over

### 10.1. Arbitrary Removal Differs from Head/Tail Operations

A linked queue does not automatically have O(1) lookup by value. To find an arbitrary object to remove, it still must locate its position. With an array queue, removing an item in the middle may require shifting the relevant references in the implementation.

Therefore, if your pattern frequently searches and cancels by job ID, evaluate that path separately. Do not measure only `put`/`take` and assume every cancellation operation has the same cost.

### 10.2. Batch Draining Does Not Create a Processing Transaction

`drainTo` can move currently available elements into a target collection for batch processing. That does not mean downstream processing is atomic or guaranteed to complete.

If the target collection or processing step fails, the application needs to know how far data was transferred. Also, do not use a target collection being modified by multiple threads without synchronization just because the source is a thread-safe queue.

Batch size is another configuration variable: large batches can change work distribution, resource holding times, and latency. When comparing the two classes, keep this variable constant or document it explicitly.

### 10.3. Iterating the Queue Is Not a Work-Claiming Mechanism

Iterators are for observation and are weakly consistent during updates. Do not iterate and treat each element as exclusively assigned to the reader.

If the actual need is to claim and remove elements from the queue, use an appropriate removal operation. If reporting on a fixed state is needed, define how to stabilize or copy the data and what consistency level is required.

Printing a plausible-looking list of elements does not prove all concurrent updates appeared in the same snapshot.

## 11. Practice Exercises to Self-Check Your Choice

### Exercise 1: What Did the Constructor Change?

An application was using `new ArrayBlockingQueue<>(200)`. The author changed it to `new LinkedBlockingQueue<>()` and saw producers waiting less.

Explain why you cannot yet conclude that the linked structure is faster. What additional measurements are needed regarding queued count, completed jobs, memory, and wait time?

Explanation guide: the data acceptance bound changed. First, compare the two configurations with the same capacity, or clearly document the policy difference being tested.

### Exercise 2: Mostly Empty Load vs. High-Turnover Load

One configuration has a very large capacity but usually holds only a few elements. Another configuration continuously has data turning over at a high rate.

Why might the two configurations have different memory trade-offs between a pre-allocated array and nodes allocated on the insertion path? What data should be collected before deciding?

Explanation guide: look at the memory of an empty array, live node count, allocation rate, reclamation impact, and payload size. Do not assign fixed byte counts or conclusions without specifying the JVM and workload.

### Exercise 3: Does Two Locks Mean Twice as Fast?

One producer and one consumer perform slow work outside the queue. Switching to a mechanism with separate put/take locks leaves total time nearly unchanged.

Does this contradict how `LinkedBlockingQueue` works? Point out which portion of time may be dominating.

Explanation guide: the opportunity to overlap queue operations does not speed up every part of the pipeline. Work outside the queue or another resource may be what determines total speed.

### Exercise 4: FIFO or Fairness?

Two consumers both take work from a FIFO queue. One completes more jobs than the other.

Can you conclude from that count alone that the queue is not FIFO? Does enabling fairness guarantee both consumers complete the same amount of work?

Explanation guide: element order, access rights when waiting, and each consumer's own processing speed are three different factors. Choose the observation that matches what you want to evaluate.

### Exercise 5: Preserving the Protocol When Switching Classes

Take `CommonQueuePipelineDemo`, replace both constructors with another shared capacity, and still keep four tasks and two stop signals.

State which functional results must hold and which properties must not be asserted: how IDs are split across consumers, runtime, fairness level, or completion order.

Next, suppose one consumer throws an error before receiving a stop signal. Is changing the queue class alone enough to make the remaining participants exit all blocking calls? What error-reporting and cancellation mechanism is needed at the coordination layer?

### Questions to Ask Before Finalizing a Choice

1. What bound does the constructor actually set?
2. What are the typical backlog level and burst level?
3. Is the cost in the queue or in the work being processed?
4. Do memory goals account for payloads, waiting producers, and in-flight work?
5. Is a separate fairness policy needed?
6. When full, does the application wait, reject, or retry within what budget?
7. Does the measurement keep capacity, workload, policy, and data identical?
8. Do the termination protocol and error handling work on both classes?

Choosing between the two classes means choosing a storage and coordination trade-off within a well-defined pipeline. A sound contract, intentional capacity, and proper measurement make the decision more grounded than a class name or a single timing result.
