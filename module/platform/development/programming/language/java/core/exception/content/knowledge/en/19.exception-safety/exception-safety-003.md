# Computing on Temporary Data Before Publishing Results

## 1. Why Prepare Results Before Mutating State?

A Java method may perform several sequential steps: validating inputs, computing new values, transforming collections, constructing objects, and finally updating state used by other methods. If active state is modified from the start, any exception thrown midway can leave the data only partially updated.

For example, a configuration manager stores a **quota** and a list of **topics**. The business requirement is that adding a topic also increases the quota accordingly. An unsafe approach is to append to the list first and compute the new quota afterward:

~~~java
// Illustrative code in a class with mutable fields:
// List<String> topics; int quota;
topics.add(topic);
quota = Math.addExact(quota, increment);
~~~

If **Math.addExact** detects an overflow, it throws **ArithmeticException** after the list has already been mutated. The caller knows the call failed, but the object's contents no longer match its prior state. Even if the second statement does not fail, a reader thread without proper synchronization can still observe piecemeal updates.

The **compute on temporary data before publishing results** pattern solves this ordering problem:

1. Read the current state **S0**.
2. Validate preconditions and compute on local variables or a private copy.
3. Construct a complete candidate state **S1** that satisfies all invariants.
4. If any preparation step fails, report the error and preserve **S0**.
5. If all preparation steps succeed, **publish S1 at a clear commit point**.

Here, **publishing** (commit) means making the new state the one used by other methods. For an in-memory object, the publish point is typically swapping a reference to an immutable snapshot. For a database, file, or distributed system, the commit point requires the mechanism appropriate to that system.

The primary goal is to **preserve observable state when an error occurs before commit**. This structure helps implement **failure atomicity** for a specific state boundary: an operation either completes with the new result, or fails with the old state intact. However, that property holds only when all changes within the promised scope are genuinely deferred until the publish point.

## 2. Distinguishing Temporary Data from Published State

| Component | Role | Requirement |
| --- | --- | --- |
| Current state S0 | Source of data currently in effect | Must not be modified during the preparation phase |
| Intermediate variables | Hold computed values such as sums, limits, or parsed data | Must not produce externally observable changes |
| Copy / builder | Holds the new data structure under construction | Must not share mutable parts that could be altered unintentionally |
| Candidate state S1 | New object containing the **entire** valid result | Invariants verified before commit |
| Publish point | Operation that replaces S0 with S1 | Explicit, without depending on multiple fallible steps |

A **temporary** value can be a local **int**, a newly created **ArrayList**, a **record**, an immutable object, or computed results held in an uncommitted transaction. Not every problem requires allocating a new object; what is mandatory is that work capable of failing must not corrupt the active state.

Three operations must be distinguished:

- **Copying:** creating a new container for data; this may be a shallow copy.
- **Finalizing and freezing the candidate:** validating correctness and preventing callers from mutating the candidate's contents after publication.
- **Publishing:** changing the state observed by the rest of the program.

Calling **new ArrayList<>(oldList)** only creates a new list. If the list's elements are mutable objects and other code still holds references to them, mutating those elements still affects the old data. A safe candidate must control both aliasing and data ownership.

## 3. Runnable Java 17+ Example: Prepare Everything, Then Swap the Snapshot

The example below builds a configuration holder with two coupled pieces of information: **quota** and **topics**. Every configuration update must keep both components consistent.

The state is encapsulated in **record Snapshot**. The record wraps **List<String>** defensively using **List.copyOf** so callers cannot add or remove topics through the published list. The **revise** method uses local variables to validate, compute, and build the candidate. Only the final statement **state = candidate** publishes the entire result.

Create the file **PublishCandidateDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class PublishCandidateDemo {
    record Snapshot(int quota, List<String> topics) {
        Snapshot {
            if (quota < 0) {
                throw new IllegalArgumentException("quota cannot be negative");
            }
            topics = List.copyOf(topics);
        }
    }

    static final class TopicSettings {
        private volatile Snapshot state =
                new Snapshot(3, List.of("core"));

        Snapshot snapshot() {
            return state;
        }

        synchronized void revise(int addedQuota, String topic) {
            Objects.requireNonNull(topic, "topic");
            String cleaned = topic.strip();
            if (cleaned.isEmpty()) {
                throw new IllegalArgumentException("topic must not be blank");
            }

            Snapshot before = state;
            int nextQuota = Math.addExact(before.quota(), addedQuota);
            if (nextQuota < 0) {
                throw new IllegalArgumentException("quota cannot be negative");
            }

            List<String> nextTopics = new ArrayList<>(before.topics());
            nextTopics.add(cleaned);
            Snapshot candidate = new Snapshot(nextQuota, nextTopics);
            state = candidate;
        }
    }

    public static void main(String[] args) {
        TopicSettings settings = new TopicSettings();
        System.out.println("Initial: " + settings.snapshot());
        Snapshot beforeInvalid = settings.snapshot();

        try {
            settings.revise(2, "   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Validation failed: " + ex.getMessage());
        }
        System.out.println("Unchanged after validation: "
                + beforeInvalid.equals(settings.snapshot()));

        settings.revise(2, "  async  ");
        System.out.println("Committed: " + settings.snapshot());
        Snapshot beforeOverflow = settings.snapshot();

        try {
            settings.revise(Integer.MAX_VALUE, "more");
        } catch (ArithmeticException ex) {
            System.out.println("Arithmetic failed: " + ex.getMessage());
        }
        System.out.println("Unchanged after overflow: "
                + beforeOverflow.equals(settings.snapshot()));
        System.out.println("Final: " + settings.snapshot());
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac --release 17 PublishCandidateDemo.java
java PublishCandidateDemo
~~~

Output:

~~~text
Initial: Snapshot[quota=3, topics=[core]]
Validation failed: topic must not be blank
Unchanged after validation: true
Committed: Snapshot[quota=5, topics=[core, async]]
Arithmetic failed: integer overflow
Unchanged after overflow: true
Final: Snapshot[quota=5, topics=[core, async]]
~~~

This output demonstrates two failure paths and one success path:

- **Invalid input:** a whitespace-only topic string is caught during preparation. **state** has not been assigned, so the snapshots before and after the error are equal.
- **Success:** the topic is normalized with **strip**, the quota is computed as **5**, the candidate list becomes **[core, async]**, and both are published in a single reference swap.
- **Overflow:** **Math.addExact(5, Integer.MAX_VALUE)** throws **ArithmeticException** before a complete candidate is published; the current snapshot remains **Snapshot[quota=5, topics=[core, async]]**.

In this program, **record** automatically generates **toString** and **equals** based on component values, making the output and snapshot comparisons clear. **List.copyOf** prevents structural modification of the list through the snapshot, and immutable **String** elements ensure this snapshot shares no mutable elements. When switching to a list of mutable objects, additional element copying or immutable design is required.

This example has been verified with **javac --release 17** and run on a compatible JDK; the output above is the actual program output.

## 4. Which Points Can Throw Exceptions During Preparation?

Explicit **throw** statements are not the only failure paths. In **revise**, several points can fail:

| Preparation step | Potential failure | Published state |
| --- | --- | --- |
| **Objects.requireNonNull** | **NullPointerException** if topic is null | S0 preserved |
| **strip** and blank check | Rejects invalid topic | S0 preserved |
| **Math.addExact** | **ArithmeticException** on int overflow | S0 preserved |
| Negative quota check | **IllegalArgumentException** | S0 preserved |
| Copying the list | May fail while building candidate data | S0 preserved under normal design assumptions |
| Creating **Snapshot** | Constructor checks invariants or rejects invalid components | S0 preserved |
| **state = candidate** | Swaps reference to the complete result | S1 becomes the current state |

Do not interpret this table as a guarantee of recovery from severe **Error**s, JVM crashes, or abrupt process termination. The table describes ordinary exception paths in an in-memory state model.

The essential point: statements that can throw exceptions sit **before** publication. If you reorder them to assign **state = candidate** first and then invoke a callback that can throw, the contract "any exception preserves S0" no longer holds. A callback failing after commit may need to be reported as a separate notification failure rather than a failure of the primary update.

## 5. Why Use a Shared Snapshot Instead of Updating Individual Fields?

Suppose a class has two separate fields:

~~~java
// Illustrative code inside a class containing mutable fields.
int quota = 3;
List<String> topics = new ArrayList<>(List.of("core"));

void reviseUnsafe(int increment, String topic) {
    topics.add(topic); // Real state has already changed.
    quota = Math.addExact(quota, increment); // May throw an exception.
}
~~~

With two separate mutable fields, you must get the ordering right and handle writing both components. Even if addition is checked first, you still have to account for errors or observers appearing between updates. If all readers must see a consistent **quota + topics** pair, bundling them into a single snapshot turns a multi-field update into a single reference publication.

Shifting to this model:

~~~text
Before preparation:  current ──► Snapshot(quota=3, topics=[core])
                                  |
Private preparation:              ▼
                       candidate(quota=5, topics=[core, async])
                                  |
Single commit:       current ─────┘
~~~

The diagram focuses on **observability**: the candidate is neither attached to **current** nor leaked through a public API. As long as all candidate data remains private, an exception while building the candidate does not alter the current snapshot.

The trade-off is that this approach may allocate objects and copy collections on every update. For large state with high update frequency, consider persistent data structures, splitting aggregates along meaningful business boundaries, or appropriate locking/transactions. Do not break consistency guarantees just to avoid an allocation before measuring an actual performance problem.

## 6. Protecting Temporary Data from Aliasing and Reference Leaks

A copy is useful only if modifying it does not mutate the original state. Distinguish the following scenarios:

### 6.1 Copying the Shell While Sharing Mutable Elements

~~~java
// Illustrative code: Task is a mutable object with setStatus(...).
List<Task> candidate = new ArrayList<>(currentTasks);
candidate.get(0).setStatus("DONE");
~~~

The new list still points to the same **Task** instances as the old list. **setStatus** mutates the shared object; the original state has already changed before commit. Private preparation requires immutable value objects, defensive copies of each element, or representing results with new values that do not touch shared objects.

### 6.2 Publishing a Collection That Someone Else Can Still Mutate

~~~java
// Illustrative code: saved is the same reference to the mutable list.
List<String> candidate = new ArrayList<>(List.of("A", "B"));
this.currentList = candidate;
candidate.add("C");
~~~

The published list continues to change after the commit point. Assigning a reference does not make a collection immutable. You can publish **List.copyOf(candidate)** when the elements are already safe and no shared mutable objects need protection. In the runnable example, **record Snapshot** always performs a defensive copy in its constructor.

### 6.3 Temporary Data Accidentally Exposed Externally

Avoid calling listeners, other caches, loggers with custom callbacks, or passing candidate references to plugins during preparation if they might retain or mutate the data or trigger side effects. Once a candidate is no longer private, **not yet assigned to state** no longer means **unobserved**.

### 6.4 Immutable Wrappers Are Not Deep Immutability

**Collections.unmodifiableList(list)** creates a view that forbids mutation through the wrapper, but direct modifications to the backing list still show through the view. **List.copyOf(list)** creates an unmodifiable list that is independent of the original mutable structure, yet it still does not deep-copy the objects inside. Choose the approach based on element mutability and reference ownership.

## 7. Publishing Results Safely in Multithreaded Programs

Two separate questions must be addressed:

1. **Does every reader observe a complete snapshot published according to memory-model rules?**
2. **Can two concurrent writers overwrite each other's changes?**

In the **PublishCandidateDemo** example:

- **volatile Snapshot state** provides visibility when one thread assigns the reference and another thread reads it. Combined with an immutable snapshot, a reader obtains a complete state at the time of the read.
- **synchronized void revise(...)** serializes updates going through this method with respect to one another. Each writer reads the preceding state and builds the new state under the same lock.
- **snapshot()** returns a single object reference read once. If you need multiple fields from the same point in time, store the returned value in a local variable and read all properties from that same snapshot; avoid calling **snapshot()** multiple times and accidentally combining data from two different versions.

Note: **volatile** enables safe publication and reading of a reference, but it does **not** automatically make a "read S0 → compute S1 → assign S1" sequence lossless under concurrent writers. Two writers can both read S0, each compute a new version, and the later write will overwrite the earlier one.

### Using AtomicReference and CAS for Optimistic Updates

Another approach is using **AtomicReference<State>**, computing a candidate from the current snapshot on each attempt, and committing only if that snapshot is still current. The following snippet is **contextual illustration**, assuming **State** is an immutable record with components **quota** and **topics**, **ref** is an **AtomicReference<State>**, and **topic** has already been validated:

~~~java
ref.updateAndGet(before -> {
    int quota = Math.addExact(before.quota(), increment);
    if (quota < 0) {
        throw new IllegalArgumentException("negative quota");
    }

    List<String> next = new ArrayList<>(before.topics());
    next.add(topic);
    return new State(quota, List.copyOf(next));
});
~~~

The updater function may be invoked **multiple times** when CAS loses a race to another writer that modified the state first. Therefore, the candidate-building function must be **free of side effects**: do not send emails, invoke payment calls, increment external counters, write files, or mutate shared objects inside the lambda. Those side effects could execute repeatedly even though only one final update is published.

If the lambda throws an exception during preparation, **updateAndGet** does not commit for that failed call. Keep in mind that updates from **other writers** may still have occurred concurrently; "my call failed" must not be interpreted as "all global state stood still."

For typical locking, a **synchronized** method like the main example is easier to read when computation cost is small. When using lock-free/CAS, evaluate retries, function purity, and published contents with realistic concurrency tests.

## 8. Design Workflow for a Prepare–Publish Operation

### Step 1: Identify the Invariants

Write down what constitutes valid state: quota is non-negative; the topic list contains no nulls; a new configuration must update both quota and topics together; published data cannot be mutated through a caller's reference.

If an invariant spans multiple fields, consider representing them as a single object/record rather than separate exposed fields.

### Step 2: Identify All Potential Failure Points

List validation, parsing, arithmetic that can overflow, constructors, collection copies, callbacks, and I/O. Do not count only statements with the **throw** keyword. If what looks like a "prepare" phase already calls an external system with side effects, separate that side effect into its own transactional problem.

### Step 3: Read and Hold a Snapshot S0

If state is already encapsulated in an immutable object, simply hold a **before** reference. If mutable fields are still separate, reading them must follow appropriate synchronization so data from different points in time is not mixed.

### Step 4: Build S1 Using Private Data

Use local variables; copy data that needs modification; construct new result objects. Do not mutate S0 directly. Avoid calling functions with unknown side effects on the original objects.

### Step 5: Verify S1 Before Commit

Ensure all acceptance conditions have been checked. The constructor of an immutable object is a good place to enforce invariants, because an instance in an invalid state cannot be constructed through normal paths.

### Step 6: Publish Once

Use a properly synchronized reference swap, or compare-and-set when there are concurrent writers. Do not split one logical change into multiple independent assignments that readers could observe piecemeal.

### Step 7: Define Post-Commit Behavior

Sending a notification or invoking a callback after commit can fail. Distinguish the **state update result** from the **notification result** so callers do not mistakenly assume a post-commit exception means the operation never happened.

## 9. Operations That Cannot Be Reduced to a Single In-Memory Assignment

This pattern is easiest to apply when the state to publish resides in an aggregate owned in one place. For external data sources, preparing ahead of time is still helpful, but it does not replace the storage engine's guarantees.

### Writing Files

If you write directly to the target file and writing is interrupted, the file may contain partial new data. One strategy is to write completely to a **temporary file**, close/verify success, and then rename/move it to the target location atomically if the filesystem supports it. Java NIO provides **Files.move** with **StandardCopyOption.ATOMIC_MOVE**; when unsupported, the operation may throw **AtomicMoveNotSupportedException**. Do not silently fall back to a non-atomic operation if the contract requires atomic replacement. Atomic file replacement also differs from durability after power loss: durability has its own requirements regarding flushing and filesystem behavior.

### Databases

Computing temporary values in the Java layer does not guarantee two **UPDATE** statements will both succeed. Use a database transaction if both statements must commit or rollback together, and verify transaction boundaries, isolation levels, constraints, and which operations actually participate in the transaction.

A classic case is transferring a balance between two accounts. If you debit account A and then credit account B, a failure in the second step leaves a half-completed state. "Computing ahead" catches input errors, but does not handle I/O failures between two separate write statements. Only an appropriate transaction provides a commit/rollback boundary for that data.

### HTTP, Queues, and Other Services

An outbound request is no longer private temporary data inside the Java process. A timeout does not prove the receiver did not perform the operation. Retrying can send duplicates and cause duplicate side effects. Mechanisms such as idempotency keys, status verification, outbox patterns, compensating workflows, and partial-success contracts are needed depending on the architecture. These measures provide different guarantees than swapping an in-memory snapshot.

## 10. When to Use Builders, Copies, and Mutable Staging?

Not every problem needs a new record for every addition:

| Scenario | Suitable preparation approach | Points to watch |
| --- | --- | --- |
| Computing a single value | Primitive or immutable local variable | Finish computing and validate before assigning the field |
| Updating multi-property configuration | Immutable candidate builder/record | Constructor validates invariants; do not expose the builder |
| Updating a collection | Copy collection, edit copy, publish immutable copy | Shallow copies and mutable elements |
| Replacing a complex object graph | Ownership-aware copy or persistent data structure | No remaining aliases that can mutate S0 |
| Multiple writers on the same snapshot | synchronized/lock or AtomicReference CAS | Avoid lost updates and retry side effects |
| Writing multiple DB records | DB transactions and constraints | Java-side staging does not replace transactions |
| Replacing file contents | Temporary file + atomic move when supported | Consider durability, cleanup, and filesystem limits |

Sometimes mutable staging is reasonable to reduce allocations: use a temporary **ArrayList** to append, sort, or filter, and call **List.copyOf** only when finalizing. That is safe when the staging list is private to the operation, not yet attached to current state, and no external reference can modify it during preparation.

A **builder** also acts as true staging only if its **build()** method produces an independent or immutable result. If the builder merely holds references pointing back to mutable collections in the current state, calling **build()** does not by itself provide a strong guarantee.

## 11. Testing State Preservation Before and After Exceptions

A good test must verify two things: **the success path publishes the expected result** and **error paths do not publish a half-built candidate**. In the runnable program above, comparing **beforeInvalid.equals(settings.snapshot())** and **beforeOverflow.equals(settings.snapshot())** directly proves the snapshots have identical contents across both failure paths.

In real unit tests, you can organize cases in a matrix:

| Scenario | Expected outcome |
| --- | --- |
| Valid topic and valid arithmetic | Publishes one exact new snapshot |
| Null topic | **NullPointerException**; state unchanged |
| Whitespace-only topic | **IllegalArgumentException**; state unchanged |
| Negative resulting quota | **IllegalArgumentException**; state unchanged |
| Quota addition overflows **int** | **ArithmeticException**; state unchanged |
| Error in candidate constructor | Faulty candidate is not published |
| Caller attempts to mutate snapshot list | Mutation is rejected; snapshot unchanged |
| Two concurrent writers update | No lost updates and no half-baked snapshot |
| Post-commit callback fails | Contract must specify whether state is already committed |

When using a test framework, capture the snapshot before the call, assert the exception with **assertThrows**, and then assert the entire state after the error. Do not stop at **assertThrows**: an operation can throw the right exception and still corrupt data.

Checking invariants alone is not always enough to prove **no change**. An object can remain valid yet be partially modified; distinguish between the **basic guarantee** ("remains valid") and the **strong guarantee** ("preserves state within the promised scope"). For multithreaded behavior, dedicated concurrency testing or linearizability analysis is needed; sequential unit tests only exercise the paths they trigger.

## 12. Common Design Mistakes

**Preparing by mutating S0 directly.** Calling **clear**, **add**, **remove**, or setters on the original data is already a mutation, even if an intermediate variable is named **candidate**. Create a separate object or collection before mutating.

**Assigning the new state too early.** A callback, calculation, or validation can throw an exception after the assignment; the caller may receive an error even though the change has already been published. Move all fallible preparation steps before the commit point and define a separate contract for post-commit steps.

**Shallow-copying an object graph.** Copying **List<Task>** while mutating the **Task** instances shared with S0 breaks candidate independence. Use immutable elements or deep-copy where genuinely needed.

**Using volatile and forgetting multiple writers.** Publishing a reference with proper visibility does not prevent lost updates. Use locks or CAS depending on contention and correctness requirements.

**Assuming exceptions roll back automatically.** **try/catch/finally** controls error paths and resource cleanup; it does not automatically restore memory, databases, or files. Recovery requires an explicitly designed state or transaction strategy.

**Allowing side effects inside a CAS lambda.** The candidate-computing function can run repeatedly on retries. The lambda must be pure in the sense that it produces no externally observable side effects and does not mutate the source snapshot.

**Mistaking atomic publication for a system-wide transaction.** A single reference swap is only the commit point of an in-memory aggregate. It does not simultaneously commit file writes, databases, message brokers, or network requests.

**Leaving guarantee boundaries unspecified.** If a post-commit event can fail, or if an operation permits partial progress, the API must document the exact state after an exception so callers can handle it properly.

## 13. Checklist When Applying to Java Code

Before finalizing a state-updating method, check each item in order:

1. **State:** is all data that must stay consistent grouped within a clear boundary?
2. **Failure paths:** have all statements capable of throwing before completion been listed?
3. **No early mutation:** does preparation leave S0 and any mutable objects S0 points to untouched?
4. **Freezing:** is the candidate protected from modification via leaked aliases, collections, or builders?
5. **Invariants:** are all invariants validated before publication?
6. **Commit point:** can you identify a single clear action that makes S1 current?
7. **Concurrency:** are visibility and lost-update prevention ensured if multiple threads write?
8. **Side effects:** do notifications, I/O, event publishing, and callbacks have a separate contract for post-commit errors?
9. **Testing:** have you compared snapshots before and after every error path and verified the success path?

This technique shifts most exception risk into the **candidate-building** phase. By keeping the old state intact until the publish point, methods become easier to reason about, test, and maintain. Its most important limitation is scope: state preservation can be claimed only when all data and side effects covered by the promise are truly governed by the corresponding commit point.