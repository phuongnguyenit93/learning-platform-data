# Distinguishing `splittable`, `jumpable`, and `leapable` Generators in Java 17

**Topic:** Java 17  
**Chapter:** Pseudo-Random Number Generators  
**Lesson:** Distinguishing splittable, jumpable, and leapable generators

When multiple tasks or multiple threads need to generate pseudo-random numbers concurrently, giving each task its own generator is not just a matter of calling `new Random()` multiple times. If generators use the same algorithm and are initialized carelessly, resulting sequences can be correlated or overlap in state space. Java 17 provides specialized interfaces in the `java.util.random` package to produce generators with similar statistical properties that follow different portions of the state cycle.

Three common organization strategies are:

- **Splittable:** calls `split()` to create a child generator from the current generator. Both parent and child generators can continue generating numbers and can be split further.
- **Jumpable:** calls `jump()` to advance the state of the generator itself forward by a huge fixed distance in the cycle. A sequence of generators can be created using `jumps()`.
- **Leapable:** extends `JumpableGenerator`, adding `leap()` to advance by an even larger distance. `leaps()` can create streams of generators in widely separated regions, which can then be further subdivided with `jump()`.

These interfaces were introduced to the standard API in Java 17 with JEP 356. They solve the problem of **distributing PRNG state for parallel computation**; they are not encryption modes, do not strictly guarantee that every generated value is distinct, and do not replace `SecureRandom` in security applications.

## 1. Context: A PRNG Has State and a Period

A PRNG is a *pseudorandom number generator*. It uses a deterministic algorithm to transform the current state into the next state and produce an output value.

A simple mental model:

```text
seed / initial state
          |
          v
        PRNG
          |
          v
     random value
          |
          v
      next state
          |
          +------> next value ...
```

Because state has a finite number of bits, a deterministic PRNG eventually returns to a previously visited state. The number of steps before the sequence repeats is called the **period**.

When there is only one execution thread, you can use a single generator object and sequentially call `nextInt()`, `nextLong()`, or `nextDouble()`. When there are multiple workers, we want each worker to use its own sequence with equivalent statistical characteristics, rather than operating concurrently on a single shared state.

### 1.1. Why Not Share a Mutable Generator?

Example:

```java
RandomGenerator random = RandomGenerator.of("L64X128MixRandom");

// Do not let multiple threads call nextLong() on one instance
// when designing separate PRNG streams per worker.
```

Most `RandomGenerator` implementations are not guaranteed to be thread-safe. Sharing can lead to state contention, schedule-dependent results, and loss of control over each worker's sequence.

A better model:

```text
                  Root generator
                        |
           +------------+------------+
           |            |            |
        Worker 1     Worker 2     Worker 3
        Own          Own          Own
        generator    generator    generator
```

The `SplittableGenerator`, `JumpableGenerator`, and `LeapableGenerator` interfaces provide different strategies for creating these separate generators.

### 1.2. "Statistical Independence" Does Not Mean Numbers Never Collide

The goal is for sequences to have nearly independent properties and distributions suited to the algorithm. Two workers can still produce the same number—for example, both producing `42`. That does not automatically prove the two sequences are duplicates or broken.

Distinguish between:

- **Duplicate output values:** Completely normal in valid random sequences.
- **Overlapping or colliding state regions:** Can make sequences dependent on each other; this is what split/jump/leap designs aim to avoid.
- **Statistical independence:** A quality target for sequences, generally achieved up to the approximation level of a given algorithm.

Do not interpret the API documentation as a guarantee that every value across every worker is unique.

## 2. Where Do the Three Interfaces Live in the Java 17 API?

The interfaces are nested interfaces inside `java.util.random.RandomGenerator`:

```java
RandomGenerator.SplittableGenerator
RandomGenerator.JumpableGenerator
RandomGenerator.LeapableGenerator
```

They all extend `RandomGenerator.StreamableGenerator`, so all can create streams of generators in appropriate ways. Important inheritance relationships:

```text
                    RandomGenerator
                           |
                  StreamableGenerator
                    /      |       \
                   /       |        \
          Splittable   Jumpable   (other streamable interfaces)
                         |
                      Leapable
```

`LeapableGenerator` **extends `JumpableGenerator`**. Therefore, a leapable generator can also jump. An ordinary jumpable generator cannot necessarily leap.

`SplittableGenerator` is a separate branch; it does not extend `JumpableGenerator` or `LeapableGenerator`.

| Interface | Primary Capability | Ways to Create Other Generators |
|---|---|---|
| `SplittableGenerator` | Splits a generator into child branches that can keep splitting | `split()`, `splits()` |
| `JumpableGenerator` | Advances state by a large fixed distance in the cycle | `jump()`, `jumps()` |
| `LeapableGenerator` | Jumps and advances even farther via leap | `jump()`, `leap()`, `jumps()`, `leaps()` |

Java 17 also has `ArbitrarilyJumpableGenerator`, a specialized interface for algorithms that can jump by a user-specified distance. This lesson focuses on the three strategies: split, jump, and leap.

## 3. Splittable: Creating Child Generators with `split()`

### 3.1. Concept

A `SplittableGenerator` can create a child generator from its current state:

```text
             Parent generator
                    |
                 split()
                 /     \
                /       \
       Parent generator  Child generator
          continues        newly created
             |                |
        generates         generates
             |                |
          split()          split()
           /  \             /  \
         ...  ...         ...  ...
```

Both objects continue serving as generators. The parent generator remains with the thread that created it; the child generator is handed to the new task. Each branch can recursively split further as needed.

Primary API:

```java
SplittableGenerator child = parent.split();
```

`split()` returns a new `SplittableGenerator`. The current generator may also mutate its own state while producing the child generator.

### 3.2. Basic Example

```java
import java.util.random.RandomGenerator.SplittableGenerator;

public class SplitBasic {
    public static void main(String[] args) {
        SplittableGenerator parent =
                SplittableGenerator.of("L64X128MixRandom");

        SplittableGenerator child = parent.split();

        System.out.println("Parent: " + parent.nextLong());
        System.out.println("Child:  " + child.nextLong());
    }
}
```

`L64X128MixRandom` is an LXM algorithm in JDK 17 supporting `SplittableGenerator`. `parent` and `child` are two separate objects; you can use one for the current task and pass the other to a forked task.

### 3.3. Using `splits()` to Create Multiple Generators

Instead of calling `split()` manually multiple times, you can create a stream:

```java
import java.util.List;
import java.util.random.RandomGenerator.SplittableGenerator;

public class SplitStream {
    public static void main(String[] args) {
        SplittableGenerator root =
                SplittableGenerator.of("L64X128MixRandom");

        List<SplittableGenerator> workers =
                root.splits(4).toList();

        for (int i = 0; i < workers.size(); i++) {
            System.out.println(
                    "Worker " + i + ": " + workers.get(i).nextLong()
            );
        }
    }
}
```

`splits(4)` creates a stream of four child generators. `toList()` has existed since Java 16 and works in Java 17.

The no-argument `splits()` creates an effectively unlimited stream; in applications, bound the count with `splits(count)` or `limit(count)` to avoid creating more generators than needed.

### 3.4. When to Choose Splittable?

Splittable is typically suitable when:

- New tasks can be spawned dynamically while the program runs.
- A worker can fork into multiple sub-workers.
- The computation structure is tree-like or recursive.
- The number of tasks is not fixed upfront.
- You want a dedicated generator belonging to each processing branch.

For instance, an algorithm subdividing data into subregions can hold one generator per branch. When a branch subdivides further, it calls `split()` on its own generator and passes the new generator to the subtask.

### 3.5. Parent Generator Ownership Rule

A splittable generator is also a mutable object. If multiple threads call `split()` concurrently on a single parent generator, you are back to the shared-state problem.

Proper model:

1. The current thread owns the parent generator.
2. When a subtask needs to be created, that thread calls `split()`.
3. The new generator is handed to the child worker.
4. The child worker uses only its own generator and may split further if needed.

Do not share one instance across multiple workers and call `split()` concurrently unless the implementation guarantees thread safety.

## 4. Jumpable: Advancing Quickly in the State Cycle

### 4.1. Concept

With `JumpableGenerator`, instead of branching via split, a generator can **jump forward by a large fixed distance** in the state cycle.

Illustrative diagram:

```text
A long state cycle:

... A ---------------- B ---------------- C ---------------- D ...

       jump distance       jump distance       jump distance
           |                   |                   |
        Worker 1            Worker 2            Worker 3
```

`jump()` mutates the state of **the calling generator itself**. It does not return a child generator.

```java
jumpable.jump();
```

The jump distance is specific to the concrete algorithm. JDK documentation describes jump as typically on the order of `2^64` steps or more; do not assume every implementation uses the exact same distance.

### 4.2. Important Methods

| Method | Meaning |
|---|---|
| `copy()` | Creates a new generator with identical internal state to the current state |
| `jump()` | Advances the current generator's state by a fixed distance |
| `copyAndJump()` | Copies the current state, jumps the source generator, then returns the copy |
| `jumpDistance()` | Returns the implementation's jump distance |
| `jumps()` | Creates a stream of generators from copies while repeatedly jumping the source state |
| `jumps(long count)` | Creates a stream with the specified number of generators |

Common point of confusion: `copy()` duplicates state; if two copies receive the exact same sequence of operations, they can produce the same result sequence. `jump()` is the operation that shifts the source generator to a different region of the cycle.

### 4.3. Example Using `jump()`

```java
import java.util.random.RandomGenerator.JumpableGenerator;

public class JumpBasic {
    public static void main(String[] args) {
        JumpableGenerator random =
                JumpableGenerator.of("Xoshiro256PlusPlus");

        long first = random.nextLong();

        random.jump();

        long afterJump = random.nextLong();

        System.out.println("Before jump: " + first);
        System.out.println("After jump:  " + afterJump);
        System.out.println("Jump distance: " + random.jumpDistance());
    }
}
```

`jump()` is not a command that generates a new random number. It moves the PRNG state far ahead in the cycle; the subsequent `nextLong()` call then retrieves a value from the post-jump state.

### 4.4. Using `jumps()` to Create Generators for Multiple Workers

```java
import java.util.List;
import java.util.random.RandomGenerator;
import java.util.random.RandomGenerator.JumpableGenerator;

public class JumpStream {
    public static void main(String[] args) {
        JumpableGenerator root =
                JumpableGenerator.of("Xoshiro256PlusPlus");

        List<RandomGenerator> workers =
                root.jumps(4).toList();

        for (int i = 0; i < workers.size(); i++) {
            System.out.println(
                    "Worker " + i + ": " + workers.get(i).nextLong()
            );
        }
    }
}
```

There is a very important API detail: `jumps()` returns `Stream<RandomGenerator>`, not `Stream<JumpableGenerator>`. Generators in the stream should be treated as `RandomGenerator`; do not cast them back assuming all of them can call `jump()`.

The default implementation builds the stream by copying the current state and repeatedly jumping the source generator. Thus, this produces generators positioned far apart in the cycle.

### 4.5. When to Choose Jumpable?

Jumpable fits when:

- The number of workers or computation branches is known in advance.
- You want to allocate widely separated state regions along a long cycle.
- You can create a batch stream of generators before starting parallel execution.
- Each worker will consume a bounded number of values within the algorithm's assumptions.

The JDK documentation describes a common strategy: create a root `JumpableGenerator`, call `jumps()` to produce a stream of generators, and assign one generator per thread.

### 4.6. Do Not Arbitrarily Jump on Generators Produced from a Stream

The `JumpableGenerator` Javadoc notes that you should not blindly call `jump()` on a generator already produced by `jumps()`. Doing so could create states overlapping with another generator already produced in the stream.

Let the root generator manage state region allocation via `jumps()`. Each received generator should be handed to a worker and used like a regular generator, unless the implementation's contract explicitly specifies how further branching works.

## 5. Leapable: Jumping Farther and Two-Level Hierarchy

### 5.1. Concept

`LeapableGenerator` extends `JumpableGenerator`, so it has both jump and leap capabilities.

- `jump()` advances state by a large fixed distance.
- `leap()` advances state by an even larger distance.

JDK documentation describes jump as typically around `2^64` steps or more, and leap as typically around `2^96` steps or more; the API guide also describes a typical leap around `2^128`. These are **illustrative scales**; actual distances depend on the algorithm and can be read via `jumpDistance()` and `leapDistance()`.

Hierarchy diagram:

```text
                   Root generator
                         |
                       leap()
                /        |        \
               /         |         \
        Generator A  Generator B  Generator C
           (jumpable)   (jumpable)   (jumpable)
              |            |            |
            jump()       jump()       jump()
           /   \         /   \        /   \
          ...  ...      ...  ...     ...  ...
```

This is leapable's strength: allocating very distant regions to large worker groups, then using jump to subdivide sub-branches inside each region.

### 5.2. Important Methods

| Method | Meaning |
|---|---|
| `jump()` | Capability inherited from `JumpableGenerator` |
| `leap()` | Advances current state by a larger distance than jump |
| `copy()` | Creates a state copy |
| `copyAndLeap()` | Copies state, leaps source generator, returns copy |
| `jumpDistance()` | Jump distance |
| `leapDistance()` | Leap distance |
| `jumps()` | Creates a stream of generators using jump steps |
| `leaps()` | Creates a stream of generators using leap steps |

A distinct API detail: `leaps()` returns `Stream<JumpableGenerator>`. Produced generators **must support jump**, but are not required to continue supporting leap. Do not assume child objects from `leaps()` can call `leap()`.

### 5.3. Example Using `leap()`

```java
import java.util.random.RandomGenerator.LeapableGenerator;

public class LeapBasic {
    public static void main(String[] args) {
        LeapableGenerator random =
                LeapableGenerator.of("Xoroshiro128PlusPlus");

        long first = random.nextLong();

        random.leap();

        long afterLeap = random.nextLong();

        System.out.println("Before leap: " + first);
        System.out.println("After leap:  " + afterLeap);
        System.out.println("Jump distance: " + random.jumpDistance());
        System.out.println("Leap distance: " + random.leapDistance());
    }
}
```

`Xoroshiro128PlusPlus` is an algorithm provided by JDK 17 with both jump and leap capabilities. Displayed distances depend on the implementation; do not rely on one fixed number across all algorithms.

### 5.4. Using `leaps()` to Create a Group of Generators

```java
import java.util.List;
import java.util.random.RandomGenerator.JumpableGenerator;
import java.util.random.RandomGenerator.LeapableGenerator;

public class LeapStream {
    public static void main(String[] args) {
        LeapableGenerator root =
                LeapableGenerator.of("Xoroshiro128PlusPlus");

        List<JumpableGenerator> workers =
                root.leaps(4).toList();

        for (int i = 0; i < workers.size(); i++) {
            System.out.println(
                    "Worker " + i + ": " + workers.get(i).nextLong()
            );
        }
    }
}
```

The resulting list has type `JumpableGenerator`. Each worker can generate numbers and jump to create subregions, but must not be assumed to have a `leap()` method.

### 5.5. Two-Level Model: Leap for Groups, Jump for Sub-Workers

Suppose a program has three simulation groups, and each group splits into multiple subtasks:

1. Create a root `LeapableGenerator`.
2. Call `leaps(3)` to create three generators in widely separated state regions.
3. Assign each generator to one group.
4. Within each group, use `jumps(n)` to create generators for the subtasks.

Model:

```text
Leapable root
   |
   +-- leaps(3)
          |
          +-- Group A: Jumpable generator
          |       |
          |       +-- jumps(...) -> task A1, A2, ...
          |
          +-- Group B: Jumpable generator
          |       |
          |       +-- jumps(...) -> task B1, B2, ...
          |
          +-- Group C: Jumpable generator
                  |
                  +-- jumps(...) -> task C1, C2, ...
```

This approach fits when a program has a clear hierarchical structure and needs sequence partitioning at two distance scales.

## 6. Direct Comparison of Splittable, Jumpable, and Leapable

| Criterion | Splittable | Jumpable | Leapable |
|---|---|---|---|
| Central operation | `split()` | `jump()` | `leap()` and `jump()` |
| Creating new generators by | Splitting state into parent and child generators | Copying state at widely separated positions in the cycle | Copying at very distant positions in the cycle |
| Source generator state | Continues in use and can keep splitting | `jump()` moves source generator forward | `leap()` moves source generator farther forward |
| Can subdivide further? | Yes, child generators are also splittable | Stream returns `RandomGenerator`; not assumed jumpable again | Stream returns `JumpableGenerator`; can jump further |
| Best suited for | Dynamic task creation, recursive forking, tree structures | Known worker count, batch allocation of state regions | Hierarchical partitioning, large groups subdivided further |
| Distance | Not described by a fixed jump distance | Typically on the order of `2^64` steps or more | Typically farther than jump, e.g. `2^96` or `2^128` depending on algorithm |
| Stream API | `splits()` | `jumps()` | `leaps()` |
| Stream element type | `SplittableGenerator` | `RandomGenerator` | `JumpableGenerator` |

### 6.1. Most Important Distinction

**Splittable creates branches.** You think in terms of task structure: a parent task needs to spawn a child task, so it splits off a child generator.

**Jumpable shifts within the cycle.** You think in terms of state regions: creating generator copies at widely separated positions to hand to workers.

**Leapable creates higher-level separation.** You need coarse-grained regions across groups, then use jump within each group.

There is no rule that leapable is always better than jumpable or splittable. It simply provides an extra capability suited to a different organizational structure.

## 7. How to Choose Algorithms in Java 17

The interfaces describe **capabilities**; a concrete implementation determines the algorithm, period, performance, and statistical properties.

Java 17 adds `RandomGeneratorFactory` to look up and instantiate generators by algorithm name or properties.

### 7.1. Common Algorithms in JDK 17

| Algorithm | Group | Common Capabilities |
|---|---|---|
| `L64X128MixRandom` | LXM | Splittable |
| `L64X256MixRandom` | LXM | Splittable |
| `L128X1024MixRandom` | LXM | Splittable |
| `SplittableRandom` | Legacy | Splittable |
| `Xoroshiro128PlusPlus` | Xoroshiro | Jumpable and Leapable |
| `Xoshiro256PlusPlus` | Xoshiro | Jumpable and Leapable |

The list of algorithms and properties may be extended by JDKs or providers; query factories in the target runtime rather than hardcoding assumptions across all environments.

### 7.2. Creating a Generator by Name

```java
import java.util.random.RandomGenerator;

public class ChooseAlgorithm {
    public static void main(String[] args) {
        RandomGenerator random =
                RandomGenerator.of("L64X128MixRandom");

        System.out.println(random.nextInt(1, 7));
    }
}
```

`RandomGenerator.of(name)` creates a generator using the named algorithm. If the name is unsupported, the factory throws `IllegalArgumentException`.

### 7.3. Checking Capabilities with `RandomGeneratorFactory`

Do not guess capabilities from the algorithm name. You can enumerate available providers:

```java
import java.util.random.RandomGeneratorFactory;

public class ListGeneratorCapabilities {
    public static void main(String[] args) {
        RandomGeneratorFactory.all().forEach(factory -> {
            System.out.printf(
                    "%-24s split=%-5s jump=%-5s leap=%-5s deprecated=%s%n",
                    factory.name(),
                    factory.isSplittable(),
                    factory.isJumpable(),
                    factory.isLeapable(),
                    factory.isDeprecated()
            );
        });
    }
}
```

Key methods:

- `name()`: algorithm name.
- `group()`: algorithm group.
- `period()`: period.
- `stateBits()`: number of state bits.
- `isSplittable()`: supports split.
- `isJumpable()`: supports jump.
- `isLeapable()`: supports leap.
- `isArbitrarilyJumpable()`: supports jumping by arbitrary distances.
- `isDeprecated()`: whether the algorithm is marked deprecated.

`RandomGeneratorFactory.all()` returns factories available in the runtime. Results can vary across JDKs or providers.

### 7.4. Choosing by Task Characteristics

| Need | Selection Direction |
|---|---|
| Single thread, no special requirements | A suitable `RandomGenerator` |
| Dynamic forking tasks, recursive branches | `SplittableGenerator` |
| Multiple workers provisioned in a batch upfront | `JumpableGenerator` or `SplittableGenerator` |
| Large group hierarchy subdivided into child workers | `LeapableGenerator`, followed by jump |
| Random numbers for keys, tokens, authentication data | `SecureRandom` |

Oracle suggests `L64X128MixRandom` as a general-purpose choice balancing speed, memory, and period in many applications without special requirements. Still, practical selection must consider workload, thread count, generator count, reproducibility needs, and system benchmarks.

## 8. Comprehensive Example: Assigning Dedicated Generators to Workers

The following example creates generators using all three strategies, then gives each task its own instance. Creating the generator lists is performed sequentially before running in parallel, so mutable root generators are never shared across workers.

Save file **`GeneratorAllocationDemo.java`**:

```java
import java.util.List;
import java.util.random.RandomGenerator;
import java.util.random.RandomGenerator.JumpableGenerator;
import java.util.random.RandomGenerator.LeapableGenerator;
import java.util.random.RandomGenerator.SplittableGenerator;
import java.util.stream.IntStream;

public class GeneratorAllocationDemo {

    private static final int TASK_COUNT = 4;

    public static void main(String[] args) {
        // 1. SPLITTABLE: create child generators per branch.
        SplittableGenerator splitRoot =
                SplittableGenerator.of("L64X128MixRandom");

        List<SplittableGenerator> splitWorkers =
                splitRoot.splits(TASK_COUNT).toList();

        // 2. JUMPABLE: create generators in widely separated regions.
        JumpableGenerator jumpRoot =
                JumpableGenerator.of("Xoshiro256PlusPlus");

        List<RandomGenerator> jumpWorkers =
                jumpRoot.jumps(TASK_COUNT).toList();

        // 3. LEAPABLE: partition large regions; child generators support jump.
        LeapableGenerator leapRoot =
                LeapableGenerator.of("Xoroshiro128PlusPlus");

        List<JumpableGenerator> leapWorkers =
                leapRoot.leaps(TASK_COUNT).toList();

        // Each index receives its own generator.
        System.out.println("SPLITTABLE");
        IntStream.range(0, TASK_COUNT).parallel().forEach(i -> {
            long value = splitWorkers.get(i).nextLong();
            System.out.println("Task " + i + ": " + value);
        });

        System.out.println("JUMPABLE");
        IntStream.range(0, TASK_COUNT).parallel().forEach(i -> {
            long value = jumpWorkers.get(i).nextLong();
            System.out.println("Task " + i + ": " + value);
        });

        System.out.println("LEAPABLE");
        IntStream.range(0, TASK_COUNT).parallel().forEach(i -> {
            long value = leapWorkers.get(i).nextLong();
            System.out.println("Task " + i + ": " + value);
        });
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 GeneratorAllocationDemo.java
java GeneratorAllocationDemo
```

The program prints one value per task for each strategy. Exact values vary with initial state, and print ordering is non-deterministic when using parallel streams.

### 8.1. Why Build Lists Before Running in Parallel?

`splitRoot`, `jumpRoot`, and `leapRoot` are all mutable generators. They are used sequentially to produce the worker generators. Afterward, each worker uses only the generator at its own index.

This pattern avoids having multiple threads mutate a single root generator. It also makes state ownership explicit:

- Preparation phase: one thread manages the root generator.
- Execution phase: each task owns its own generator.
- No single generator instance has `nextLong()` called by multiple workers.

If tasks fork dynamically at runtime, `SplittableGenerator` may fit better because each worker can split from the generator it owns.

## 9. Limits and Safety Rules When Partitioning Sequences

### 9.1. Do Not Share Mutable Instances Across Threads

This is the most important rule. Distribute a dedicated generator to each worker, and do not allow multiple threads to mutate the state of the same generator unless the implementation guarantees thread safety.

### 9.2. Jump/Leap Distances Are Not Infinite Regions

If a generator created from a fixed jump interval generates values far beyond its intended allocation, its sequence can advance into another generator's region. API docs state assumptions about how many values each generator produces relative to jump distance and period.

Therefore:

- Choose an algorithm with a suitable period.
- Understand the usage limits of the algorithm.
- Do not assume every child generator can emit infinitely many values while keeping regions disjoint.
- For long simulations, calculate sample counts and partition distances.

### 9.3. Split/Jump/Leap Are Not Security Mechanisms

PRNGs in this group primarily serve simulations, games, scientific computing, and parallel tasks. They are typically **not cryptographically secure**.

Do not use them to generate:

- Passwords or secret keys.
- Session tokens.
- Reset tokens.
- OTPs or verification codes.
- Nonces needing unpredictability in security protocols.

Use `java.security.SecureRandom` for requirements needing a cryptographically secure PRNG.

### 9.4. Reproducing Results in Parallel Runs

If you need to replay a run for debugging:

- Choose an explicit algorithm rather than relying on the default generator.
- Record the seed and JDK/implementation version when applicable.
- Assign generators by stable task ID.
- Do not depend on the order in which workers are scheduled.
- Do not arbitrarily vary the number of random calls between branches if reproducible sequences are needed.

The same seed does not automatically ensure two parallel programs yield identical results if generator allocation order or number consumption order changes.

## 10. Common Misconceptions

### 10.1. "Splittable and jumpable both just create a copy"

Not quite. `split()` creates a child generator according to the algorithm's splitting strategy; `jump()` shifts the current generator's state. It is the `jumps()` stream that creates copies at post-jump positions.

### 10.2. "Jumpable can leap"

No. `JumpableGenerator` only provides jump. `LeapableGenerator` extends it and adds leap.

### 10.3. "Leapable is a completely separate interface"

No. `LeapableGenerator extends JumpableGenerator`, so every leapable generator also has jump capability.

### 10.4. "`jumps()` returns a stream of JumpableGenerator"

No. In Java 17, the return type of `jumps()` is `Stream<RandomGenerator>`. Do not cast elements to `JumpableGenerator`.

### 10.5. "`leaps()` returns a stream of LeapableGenerator"

No. `leaps()` returns `Stream<JumpableGenerator>`. Child generators must be jumpable, but are not required to be leapable.

### 10.6. "Split/jumped/leaped sequences are guaranteed never to produce overlapping values"

False. Sequences aim for statistical independence; output values can still coincide by chance. The goal is to reduce correlation and avoid improper overlapping of state regions.

### 10.7. "You can share one generator across threads as long as you call split"

Do not share the same parent generator across threads. Let one thread own the parent generator, call split when forking, and hand the child generator to the new worker.

### 10.8. "Child generators from `leaps()` can keep leaping"

There is no such guarantee. The return type is `JumpableGenerator`. Rely only on the methods promised by the return type.

### 10.9. "These generators can be used for security tokens"

No. Use `SecureRandom` for sensitive data and cryptographic security requirements.

## 11. Practical Selection Workflow

When designing a multithreaded system, follow these steps:

1. **Determine the purpose:** simulation, game, test, statistics, or security. If security, choose `SecureRandom`.
2. **Determine task structure:** dynamic recursive forking or batch-allocated workers.
3. **Choose the interface:** `SplittableGenerator` for dynamic forking; `JumpableGenerator` for fixed-distance cycle partitioning; `LeapableGenerator` for two levels of distance.
4. **Choose the algorithm:** use `RandomGeneratorFactory` to inspect capabilities and properties.
5. **Create dedicated generators:** each worker owns its own instance.
6. **Estimate generation volume:** keep each worker within the algorithm's jump-distance/period assumptions.
7. **Test and benchmark:** evaluate speed, memory, worker count, and statistical properties suitable for the application.

### Quick Decision Table

| Question | If Answer Is "Yes" | Recommendation |
|---|---|---|
| Do tasks continuously fork into new subtasks? | Yes | Splittable |
| Is worker count known upfront and needing batch state-region allocation? | Yes | Jumpable |
| Are there multiple large groups, each splitting into child workers? | Yes | Leapable at group level, jump at child level |
| Is there only a single thread? | Yes | An appropriate `RandomGenerator`, no split/jump/leap needed |
| Need to generate unpredictable keys or tokens? | Yes | `SecureRandom` |

## 12. Practice Exercises

### Exercise 1. Choosing an Interface for Dynamic Forking Tasks

A worker processes a data tree. During traversal, each node may spawn from 0 to many subtasks. Each task needs its own pseudo-random sequence.

**Suggested Answer:** `SplittableGenerator` fits because each worker can call `split()` when forking and pass the child generator to the new task.

### Exercise 2. Choosing an Interface for a Fixed Batch

A simulation starts with 32 known workers. Generators must be created in widely separated regions of the cycle.

**Suggested Answer:** You can use `JumpableGenerator` and `jumps(32)`, or splittable if the partitioning matches the algorithm. With jump, verify each worker's expected sample count against the jump distance.

### Exercise 3. Two-Level Partitioning

A program has 8 experiment groups; each group has 16 workers.

**Suggested Answer:** You can use `LeapableGenerator` to create 8 group generators via `leaps(8)`, then use `jumps(16)` on each group generator. Remember that elements of `leaps()` are `JumpableGenerator`.

### Exercise 4. Reading Return Types

Given:

```java
LeapableGenerator root = LeapableGenerator.of("Xoroshiro128PlusPlus");
var children = root.leaps(4);
```

**Question:** Is every element of `children` guaranteed to be a `LeapableGenerator`?

**Answer:** No. `leaps()` returns `Stream<JumpableGenerator>`. Elements must support jump, not necessarily leap.

### Exercise 5. Explaining Why Generators Should Not Be Shared

A developer declares a `SplittableGenerator root` variable and lets all threads call `root.split()` simultaneously.

**Answer:** This shares a mutable object across multiple threads. Let one thread own the root generator and perform splits before handing child generators to workers; or use per-branch generator ownership.

### Exercise 6. Distinguishing Value Collision and Sequence Collision

Two workers both generate the value `17` on their first call.

**Answer:** This can happen naturally and does not prove the sequences are identical. Examine statistical properties and state regions, not just a single output value.

### Exercise 7. Choice for Login Tokens

A system needs to generate unpredictable login session tokens.

**Answer:** Use `SecureRandom`. `SplittableGenerator`, `JumpableGenerator`, and `LeapableGenerator` primarily serve computational PRNGs, not cryptographic security mechanisms.

## 13. Official References

- [JDK 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): base interface and generation methods.
- [JDK 17 API — SplittableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.SplittableGenerator.html): `split()`, `splits()`, and rules for creating child generators.
- [JDK 17 API — JumpableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.JumpableGenerator.html): `jump()`, `copy()`, `jumps()`, and jump distance.
- [JDK 17 API — LeapableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.LeapableGenerator.html): inheritance from Jumpable, `leap()`, `leaps()`, and leap distance.
- [JDK 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): choosing algorithms and querying splittable, jumpable, and leapable capabilities.
- [Oracle Java 17 — Pseudorandom Number Generators](https://docs.oracle.com/en/java/javase/17/core/pseudorandom-number-generators.html): using generators in multithreaded applications and algorithm selection suggestions.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): PRNG API design added in Java 17.

**Takeaway:** `SplittableGenerator` creates child generators via `split()` and fits dynamically forking tasks. `JumpableGenerator` shifts state by a fixed distance and builds a stream of generators via `jumps()`. `LeapableGenerator` extends jumpable and adds a larger leap step for hierarchical partitioning. Give each worker its own generator, verify the actual stream return types, and use `SecureRandom` for all security needs.
