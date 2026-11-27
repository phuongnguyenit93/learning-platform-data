# Reproducing Experiments by Algorithm, Seed, and Call Order in Java 17

> **Topic:** Java 17  
> **Chapter:** Pseudo-Random Number Generators  
> **Goal:** Design pseudo-random number generation programs capable of replaying results by specifying the algorithm, seed, and call order; understand the impact of generator state, parallel threads, and API choices in Java 17.

## 1. Why Can the Same Program Produce Different Random Results?

When writing simulations, tests, sample data generators, or running experiments, we often need values that appear random:

- Generating simulated user data.
- Sampling randomly from a dataset.
- Simulating dice, queues, waiting times, or failure probabilities.
- Initializing weights in optimization algorithms.
- Injecting noise to evaluate model robustness.

Example:

```java
import java.util.Random;

public class RandomDemo {
    public static void main(String[] args) {
        Random random = new Random();
        System.out.println(random.nextInt(100));
    }
}
```

Each time it runs, the program may print a different number because Random's no-argument constructor initializes its seed automatically. This is useful when independent runs are desired, but makes it hard to reproduce a bug or compare two versions of an algorithm.

To **reproduce an experiment**, at least three factors must be controlled:

1. **Algorithm:** which class/generator produces the pseudo-random number sequence?
2. **Seed:** what value initializes the starting state?
3. **Call sequence:** which generation methods are called in what order, with what parameters?

Saving only the seed without recording the algorithm and call flow is not enough to guarantee replay. Two different generators given the same seed usually produce two different sequences; the same generator with one extra nextInt() call before sampling also shifts all subsequent values.

## 2. What Is a PRNG? What Is the Role of a Seed?

A **PRNG (Pseudo-Random Number Generator)** is a generator of pseudo-random numbers. It uses an initial state and a deterministic algorithm to produce a sequence of values with random-like statistical properties within its design scope.

For a deterministic algorithm:

```text
seed + algorithm + call state
                  |
                  v
       pseudo-random value sequence
```

If two generators of the same algorithm are initialized with the same seed and then perform the same sequence of calls in the same order, they can reproduce the exact same result sequence under that generator's contract.

### 2.1. The Seed Is Not the First Random Output

A seed is data used to initialize a PRNG's state. For example:

```java
Random random = new Random(20261115L);
```

20261115L is the seed. It does not mean the first returned value will be 20261115. The generator transforms the seed through an internal algorithm before producing numbers.

You can pick any fixed seed for an experiment. What matters is saving the exact seed, data type, and initialization method.

### 2.2. Same Seed Does Not Mean Every Generator Produces the Same Sequence

```java
Random first = new Random(12345L);
Random second = new Random(12345L);

System.out.println(first.nextInt());
System.out.println(second.nextInt());
```

Two objects of the same Random class with the same seed will yield the same results at corresponding calls.

However, you cannot conclude that:

```java
Random random = new Random(12345L);
SplittableRandom split = new SplittableRandom(12345L);
```

will produce the same sequence. Random and SplittableRandom use different algorithms and internal states. **A seed only has meaning together with a specific algorithm.**

### 2.3. Why Should You Not Use Current Time as an Experiment Seed?

Example:

```java
Random random = new Random(System.currentTimeMillis());
```

Each run at a different time will usually have a different seed. If a bug appears during that run, logging only the output without logging the seed makes exact replay difficult.

For experiments needing reproducibility, accept the seed from configuration or command-line arguments:

```java
long seed = 20261115L;
Random random = new Random(seed);
```

If the goal is to produce different sequences on each run, automatic seeding may fit. Still, log the seed used if you may need to replay a specific run later.

## 3. java.util.Random: A Familiar Generator with a Specified Algorithm

java.util.Random is a simple choice with a long-standing contract. Java specifies this class's algorithm so that the same seed and same call sequence produce the same number sequence across conforming Java implementations.

### 3.1. Initializing with a Fixed Seed

```java
import java.util.Random;

public class ReproducibleRandom {
    public static void main(String[] args) {
        long seed = 12345L;
        Random random = new Random(seed);

        for (int i = 0; i < 5; i++) {
            System.out.println(random.nextInt(100));
        }
    }
}
```

Each time the program runs, with the same Java API and call order, the five generated numbers will be identical. If you recreate the object:

```java
Random firstRun = new Random(12345L);
Random replay = new Random(12345L);

for (int i = 0; i < 5; i++) {
    int a = firstRun.nextInt(100);
    int b = replay.nextInt(100);
    System.out.println(a == b);
}
```

The output consists of five lines of true.

### 3.2. Random Uses a 48-Bit LCG

To understand why call order matters, look at Random's core mechanism. It uses a form of **Linear Congruential Generator (LCG)** with a 48-bit state.

Specified constants:

```java
private static final long multiplier = 0x5DEECE66DL;
private static final long addend = 0xBL;
private static final long mask = (1L << 48) - 1;
```

When initialized with seed s, the internal state is set by the formula:

```java
state = (s ^ multiplier) & mask;
```

Each bit-generation step updates the state:

```java
state = (state * multiplier + addend) & mask;
```

Then the high bits of state are extracted as intermediate results. Methods such as nextInt, nextLong, nextDouble, and others use this mechanism according to their own rules.

This is a deterministic algorithm. The same state and same number of update steps produce the same state sequence. Thus, an inserted generation call shifts all subsequent results.

**Note:** This is a description of java.util.Random's specified internal algorithm, not a guide to reimplementing PRNGs in applications. Always use the official API.

### 3.3. A long Seed, Yet Random's State Is 48-Bit

Although the constructor accepts a long, Random's LCG algorithm only holds a 48-bit state. Seed scrambling and masking mean that some distinct seed values can map to the exact same initial state.

Therefore:

- A seed is an application-managed run identifier, not a cryptographic key.
- Do not assume two distinct long seeds always create two distinct internal states.
- If a generator with larger state or different statistical properties is needed, consider Java 17's generator APIs.

### 3.4. Use nextInt(bound) Instead of Modulo

When you want an integer from 0 to bound - 1, use:

```java
int index = random.nextInt(10); // 0..9
```

Do not write manually:

```java
int index = Math.abs(random.nextInt()) % 10; // Avoid
```

Modulo division can produce a skewed distribution because the signed integer domain is not divisible by 10; Math.abs(Integer.MIN_VALUE) is also a special case that cannot become positive in int. nextInt(bound) handles bounds and avoids modulo bias per the API contract.

## 4. Call Order Determines Each Value's Position in the Sequence

A typical PRNG changes state after every call. Consequently, keeping the same seed while changing call order alters which value gets bound to which variable.

### 4.1. Two Runs with the Same Seed but Different Call Orders

```java
import java.util.Random;

public class CallOrderDemo {
    public static void main(String[] args) {
        long seed = 99L;

        Random first = new Random(seed);
        int firstA = first.nextInt(100);
        int firstB = first.nextInt(100);

        Random second = new Random(seed);
        int secondB = second.nextInt(100);
        int secondA = second.nextInt(100);

        System.out.println("firstA  = " + firstA);
        System.out.println("firstB  = " + firstB);
        System.out.println("secondB = " + secondB);
        System.out.println("secondA = " + secondA);
    }
}
```

In the first run, the first number is assigned to firstA and the second to firstB. In the second run, those same two numbers are assigned to the variables in reverse order. Thus, the seed is identical, yet the **data meaning attached to each value** has changed.

### 4.2. Inserting a Call in the Middle Shifts Subsequent Values

```java
Random original = new Random(7L);
int a1 = original.nextInt(100);
int b1 = original.nextInt(100);

Random changed = new Random(7L);
int a2 = changed.nextInt(100);
int ignored = changed.nextInt(); // New call
int b2 = changed.nextInt(100);
```

a1 and a2 match because both are the first call. However, b1 and b2 usually differ: changed advanced its state before generating the second value.

A seemingly minor code change can break reproducibility:

- Adding a random value for logging or debugging.
- Adding a conditional branch that occasionally calls nextInt.
- Changing a sampling algorithm such that the generator call count changes.
- Adding a data-initialization step sharing the generator before running the experiment.

### 4.3. Parameter Sequence Is Also Part of the Experiment

Bounded methods such as nextInt(bound) may consume different numbers of bits depending on bound and rejection sampling. Therefore, replacing:

```java
int a = random.nextInt(10);
```

with:

```java
int a = random.nextInt(1000);
```

does not only change the result domain; it can alter the subsequent state used in the sequence. To replay an experiment, preserve both **method types and parameters**.

## 5. Practical Example: Reproducing a Multi-Step Experiment

Suppose we simulate a run with three steps:

1. Choose the request count.
2. Choose a simulated delay.
3. Decide whether a request fails.

Create the file ExperimentDemo.java:

```java
import java.util.Random;

public class ExperimentDemo {

    static void runExperiment(long seed) {
        Random random = new Random(seed);

        int requestCount = 10 + random.nextInt(11);
        int delayMillis = 50 + random.nextInt(451);
        boolean failed = random.nextDouble() < 0.1;

        System.out.println("seed=" + seed);
        System.out.println("requestCount=" + requestCount);
        System.out.println("delayMillis=" + delayMillis);
        System.out.println("failed=" + failed);
    }

    public static void main(String[] args) {
        runExperiment(20261115L);
        System.out.println("--- replay ---");
        runExperiment(20261115L);
    }
}
```

Compile and run:

```bash
javac --release 17 ExperimentDemo.java
java ExperimentDemo
```

Both output blocks will match because each call to runExperiment:

- Initializes a new Random with the same seed.
- Calls the same generation methods.
- Passes the same bounds.
- Calls the methods in the same order.

If you later add a random call before delayMillis, the delay result and failure decision will change. That is why the call sequence should be managed as part of experiment design.

### 5.1. Separating Generators by Purpose

If an experiment has multiple independent components, you can create a separate generator for each component:

```java
long masterSeed = 20261115L;

Random requestGenerator = new Random(masterSeed);
Random delayGenerator = new Random(masterSeed + 1);
Random failureGenerator = new Random(masterSeed + 2);
```

Then adding a call to requestGenerator does not shift the sequences of delayGenerator or failureGenerator.

This is a simple way to reduce coupling between parts. In larger applications, establish an explicit child-seed derivation rule, avoiding arbitrary or potentially colliding values. You can use SplittableRandom to split generators systematically or a seed-mixing function specified in the project.

### 5.2. Recording Metadata for Replay

An experiment result should record at minimum:

| Field | Example | Reason |
|---|---|---|
| seed | 20261115 | Restore initial state |
| algorithm | java.util.Random | Identify PRNG used |
| javaVersion | 17.0.x | Record runtime environment |
| experimentVersion | experiment-v3 | Identify experiment logic |
| inputDataset | dataset-2026-11 | Pin input data |
| callProtocol | request → delay → failure | Record call order and parameters |
| parallelism | 1 | Record execution strategy |

Example log:

```text
experiment=load-test
experimentVersion=v3
algorithm=java.util.Random
seed=20261115
javaVersion=17.0.x
callProtocol=requestCount:nextInt(11);delay:nextInt(451);failure:nextDouble()
parallelism=1
dataset=dataset-2026-11
```

Version values here are illustrative placeholders; record the actual values from runtime. Logging seed and call protocol is far more useful than logging output numbers alone.

## 6. SplittableRandom: Creating Independent Random Streams for Parallel Computing

java.util.SplittableRandom is designed for scenarios needing multiple child generators, especially in parallel processing.

Unlike Random, SplittableRandom is **not thread-safe**. Do not share the same instance across multiple threads simultaneously.

### 6.1. Creating a Generator with a Fixed Seed

```java
import java.util.SplittableRandom;

public class SplitDemo {
    public static void main(String[] args) {
        SplittableRandom random = new SplittableRandom(12345L);

        for (int i = 0; i < 5; i++) {
            System.out.println(random.nextInt(100));
        }
    }
}
```

With the same seed and same call order, the program can reproduce the result sequence under SplittableRandom's contract.

### 6.2. Splitting Child Generators with split()

```java
SplittableRandom root = new SplittableRandom(12345L);

SplittableRandom workerA = root.split();
SplittableRandom workerB = root.split();

int sampleA = workerA.nextInt(100);
int sampleB = workerB.nextInt(100);
```

split() returns a new generator split from the parent generator's state. Child generators are designed to produce statistically independent sequences suitable for different tasks.

To reproduce results, preserve:

- Root generator seed.
- Number of split() calls.
- Order of split() calls.
- Which child generator is assigned to which task.
- Call order inside each child generator.

### 6.3. Proper Pattern for Replayable Parallel Tasks

Split child generators **sequentially first**, then assign each generator to a task:

```java
import java.util.SplittableRandom;
import java.util.concurrent.CompletableFuture;

public class ParallelReplayDemo {

    static long simulate(SplittableRandom random) {
        long total = 0;
        for (int i = 0; i < 1_000; i++) {
            total += random.nextInt(1_000);
        }
        return total;
    }

    public static void main(String[] args) {
        SplittableRandom root = new SplittableRandom(987654321L);

        // Split in deterministic order before submitting tasks.
        SplittableRandom randomA = root.split();
        SplittableRandom randomB = root.split();

        CompletableFuture<Long> taskA =
                CompletableFuture.supplyAsync(() -> simulate(randomA));
        CompletableFuture<Long> taskB =
                CompletableFuture.supplyAsync(() -> simulate(randomB));

        // Read results by task identity, not completion order.
        long resultA = taskA.join();
        long resultB = taskB.join();

        System.out.println("A=" + resultA);
        System.out.println("B=" + resultB);
    }
}
```

Both tasks run in parallel, yet each task owns its own generator. As long as the root seed, split order, code inside each task, and input data do not change, results tied to task A and task B can be reproduced. **Whether task A or B finishes first does not determine the number sequence**, provided they do not share generators and no other shared state affects results.

Do not let each thread call root.split() on the same SplittableRandom. This class is not thread-safe; split order would depend on scheduling and could cause race conditions.

### 6.4. Splitting by Work Structure

For experiments decomposed into groups, use a fixed rule:

```text
master seed
    |
    +-- split for group A
    |       +-- calls of A
    |
    +-- split for group B
            +-- calls of B
```

Avoid assigning generators by thread ID or the order threads are created by the scheduler. A task may run on a different thread between runs; experiment data identity must attach to a **stable task/partition**, not an ephemeral thread.

## 7. The RandomGenerator API in Java 17

Java 17 adds the java.util.random package and the RandomGenerator interface (JEP 356). This API provides a common way to use many PRNG algorithms rather than depending directly on each concrete class.

Familiar classes like Random, SplittableRandom, and ThreadLocalRandom also integrate with the RandomGenerator ecosystem.

### 7.1. Using the Common Interface

```java
import java.util.random.RandomGenerator;

public class GeneratorInterfaceDemo {
    static void printSamples(RandomGenerator random) {
        System.out.println(random.nextInt(100));
        System.out.println(random.nextDouble());
        System.out.println(random.nextBoolean());
    }
}
```

printSamples does not depend on a specific PRNG class. The caller can pass Random, SplittableRandom, or another suitable implementation.

However, if reproducibility is the goal, declaring only the RandomGenerator type is not enough. You must record the **actual implementation/algorithm** passed in.

### 7.2. Choosing an Algorithm with RandomGeneratorFactory

Java 17 provides RandomGeneratorFactory to look up and instantiate generators by algorithm name:

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class FactoryDemo {
    public static void main(String[] args) {
        long seed = 20261115L;

        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator random = factory.create(seed);

        for (int i = 0; i < 5; i++) {
            System.out.println(random.nextInt(100));
        }
    }
}
```

Here:

- The name L64X128MixRandom identifies the algorithm selected in the runtime.
- factory.create(seed) creates a generator with a specific seed.
- The RandomGenerator reference type lets code use common generation methods.

LXM algorithms are among the generators provided in Java 17. You can list the names offered by the current runtime:

```java
RandomGeneratorFactory.all()
        .map(RandomGeneratorFactory::name)
        .sorted()
        .forEach(System.out::println);
```

### 7.3. Why Record the Algorithm Name Too?

Metadata:

```text
seed = 12345
algorithm = L64X128MixRandom
```

carries much more information than:

```text
seed = 12345
```

Different RandomGenerator implementations have different algorithms and state. Furthermore, RandomGeneratorFactory's API documentation allows implementations to be refined across Java releases; algorithm names remain stable, yet you should not assume every bit-level detail of every implementation is immutable across all runtime versions.

If long-term exact reproduction is needed:

- Select a concrete algorithm, not an implicit default.
- Record the algorithm name and Java/vendor runtime version.
- Pin the runtime version or verified generator in the experiment workflow.
- If long-term portability at the Java API level is required, java.util.Random has the advantage that its algorithm is explicitly specified.
- If another algorithm is needed, read the implementation's contract and proactively test across the runtime versions the project supports.

## 8. Choosing a Generator by Purpose

| API | Characteristics | When to Use |
|---|---|---|
| java.util.Random | 48-bit LCG, thread-safe, long-specified algorithm | Simple experiments needing easy replay and stable sequences under Java's contract |
| java.util.SplittableRandom | Supports split, not thread-safe | Splitting PRNG streams for independent tasks, especially in structured parallel computation |
| java.util.random.RandomGenerator | Common interface across many generators | Writing APIs receiving a generator from callers, decoupling algorithm from logic |
| RandomGeneratorFactory | Look up/create generators by algorithm name | Explicitly selecting an algorithm and recording the generator name in metadata |
| ThreadLocalRandom | Thread-bound generator, optimized for concurrent access; does not allow user seeding | General multithreaded tasks not needing sequence replay |
| SecureRandom | PRNG for security requirements, with entropy sources and dedicated seeding | Tokens, nonces, keys, or security data; not for replaying experiments |
| Math.random() | Simple API using an internal pseudo-random source, no direct seed parameter | Small examples needing no generator management; unsuitable when controlled replay is needed |

There is no "best" generator for all situations. Start from requirements:

- Need simple, portable replay? Consider Random.
- Need multiple independent streams for simulation? Consider SplittableRandom.
- Need to choose a modern algorithm by name? Consider RandomGeneratorFactory.
- Need security? Use SecureRandom, never fixed seeds.
- Need multithreaded throughput without caring about replay? ThreadLocalRandom may fit.

## 9. APIs Easily Misunderstood When Reproducibility Is Needed

### 9.1. Math.random()

Math.random() returns a double in `[0.0, 1.0)`. It is convenient for small examples:

```java
double probability = Math.random();
```

However, there is no seed parameter or generator object for the application to control state directly. If replay is needed:

```java
Random random = new Random(12345L);
double probability = random.nextDouble();
```

### 9.2. ThreadLocalRandom

ThreadLocalRandom.current() gets the generator bound to the current thread. This API does not offer arbitrary seeding like new Random(seed); calling setSeed on ThreadLocalRandom throws UnsupportedOperationException.

This avoids contention when multiple threads generate numbers, yet makes sequence control for reproducible experiments difficult. Nor should you think a thread-bound seed binds to a logical task: the same task may run on a different thread in another execution.

### 9.3. SecureRandom

SecureRandom is designed for security purposes. It may gather entropy from the system and mix additional seeds into its state. Calling setSeed does not turn it into a portable simulation PRNG that replays under the same contract as Random.

Do not use SecureRandom for simulations needing replay; likewise, do not use Random, SplittableRandom, or ThreadLocalRandom to generate passwords, security tokens, or cryptographic keys.

### 9.4. No-Argument Constructors

```java
new Random()
new SplittableRandom()
```

Neither form shows a fixed seed in code. If you use them, log the seed/state via a controllable mechanism; better yet, pass a seed stored in experiment configuration.

## 10. nextGaussian() and Method-Dependent State

Not every generation method consumes a single state step in an obvious way.

For instance, Random.nextGaussian() uses a normal-distribution generation mechanism that caches one value for the next call. That means the call order of different methods can affect how values are generated and consumed.

```java
Random random = new Random(42L);

double firstGaussian = random.nextGaussian();
int nextInteger = random.nextInt(100);
```

When modifying a call sequence, explicitly record methods such as:

- nextInt(bound)
- nextLong()
- nextDouble()
- nextBoolean()
- nextGaussian()
- nextBytes(byte[])

A method may consume one or more parts of internal state; some methods also cache state. Therefore, do not merely count generic "random calls." Record **method names, parameters, and order**.

## 11. Reproducing When There Are Conditional Branches

Suppose:

```java
if (random.nextDouble() < 0.5) {
    int bonus = random.nextInt(100);
}

int result = random.nextInt(100);
```

If conditional branches differ between two runs, the number of generator calls differs. As a result, result may draw a different element from the sequence.

In an experiment comparing two algorithms, consider:

1. Using the same initial seed for each run.
2. Pre-generating random input data and saving it, then running both algorithms on the same dataset.
3. Or separating dedicated generators for each data source/branch so a change in one does not shift independent parts.
4. Explicitly documenting if call counts depend on conditional branches.

Example generating a dataset once:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

static List<Integer> createDataset(long seed, int size) {
    Random random = new Random(seed);
    List<Integer> values = new ArrayList<>();
    for (int i = 0; i < size; i++) {
        values.add(random.nextInt(1_000));
    }
    return List.copyOf(values);
}
```

Then both algorithm A and B receive the exact same list. This separates differences caused by **input data** from differences caused by **algorithm logic**.

## 12. Seed, Data, and Experiment Results: What to Save?

So others can replay runs, save a simple manifest:

```yaml
experiment:
  id: "queue-simulation-001"
  version: "v2"
  seed: 20261115
  generator:
    class: "java.util.Random"
    algorithm: "48-bit LCG specified by java.util.Random"
  runtime:
    java: "17"
    vendor: "record actual runtime vendor"
  input:
    dataset: "queue-input-v4"
    checksum: "record actual checksum"
  execution:
    parallelism: 1
    callOrder:
      - "nextInt(11): requestCount"
      - "nextInt(451): delay"
      - "nextDouble(): failureDecision"
```

This is an illustrative structure, not a mandatory Java configuration file. Replace vendor/checksum placeholders with actual values.

Record:

- Exact numeric seed (and type, e.g. long).
- Generator class/algorithm name.
- Java runtime/version/vendor if comparing across environments.
- Call order and parameters, including branches that may make extra calls.
- Dataset or dataset generation method, with a checksum if data is large.
- Source code version/commit of the experiment.
- Parallelism configuration and split/child-seed rules.
- Locale, timezone, and rounding if they affect output.

### 12.1. Should You Only Save the Generated Random Numbers?

Saving generated numbers can help replay the exact dataset without depending on the PRNG. However, it does not completely replace metadata:

- If you want to verify the generator or data generation algorithm, you still need the seed and generator name.
- If you want to replay a bug, you need to know which number corresponded to which step.
- If data is large, you can store the dataset as a separate artifact and record its checksum.

In critical experiments, the reliable approach is saving both **reproducibility metadata** and the **actual inputs** used for the run.

## 13. Design Principles for Reproducible Experiments

### 13.1. Make the Seed an Input Parameter

Avoid hiding the seed inside a no-argument constructor. Allow rerunning with the same seed:

```java
static void run(long seed) {
    Random random = new Random(seed);
    // Run experiment
}
```

The seed should be logged at the start of the experiment, before any error can occur.

### 13.2. One Random Source per Purpose

Separate generators by function (generating data, choosing failure branches, adding noise) so editing one component does not shift the entire sequence of another. Child-seed derivation rules must be stable and recorded.

### 13.3. Do Not Arbitrarily Share Mutable Generators Across Threads

Random is thread-safe, yet sharing one generator across threads still makes which thread gets which number depend on scheduling. SplittableRandom is not thread-safe, so create a separate instance for each task.

### 13.4. Distinguish Execution Order from Result Collection Order

If tasks run in parallel, completion timing can vary. Store results by task ID/partition ID and merge in a fixed logical order, not by callback completion order.

### 13.5. Do Not Change Algorithms Without Updating Metadata

Switching from Random to L64X128MixRandom while keeping the same seed changes the algorithm. Record a new experiment version or updated generator field so two runs are not confused.

### 13.6. Fixed Seeds Are Not Security

If seed and algorithm are known, the PRNG sequence can be predicted. Do not use fixed seeds to generate session tokens, passwords, verification codes, or keys.

## 14. Practice Exercises

### Exercise 1 — Producing Two Identical Runs

Write a method:

```java
static int[] generate(long seed, int count) {
    // Return count integers in [0, 99].
}
```

Requirements:

- Use Random initialized with the passed seed.
- Call nextInt(100) exactly once per element.
- Create two arrays with the same seed and compare element by element.

**Suggested Solution:**

```java
import java.util.Random;
import java.util.Arrays;

static int[] generate(long seed, int count) {
    Random random = new Random(seed);
    int[] values = new int[count];
    for (int i = 0; i < count; i++) {
        values[i] = random.nextInt(100);
    }
    return values;
}

int[] first = generate(2026L, 10);
int[] second = generate(2026L, 10);
System.out.println(Arrays.equals(first, second)); // true
```

### Exercise 2 — Demonstrating That Call Order Matters

Create two generators with the same seed. On the first generator, call nextInt(100) twice. On the second generator, call nextInt(100), then call nextDouble(), then call nextInt(100).

Compare the second integer from both generators. Explain why the results typically differ.

### Exercise 3 — Separating Streams by Purpose

Write a simulation with two sources:

- Generator A generates user counts.
- Generator B generates processing times.

Insert a new call into generator A and verify that B's sequence stays unchanged when using independent seeds.

### Exercise 4 — Creating a Generator by Algorithm in Java 17

Use RandomGeneratorFactory.of("L64X128MixRandom") to create a generator with a fixed seed. Print the algorithm name from the factory and generate five bounded integers. Rerun the program to observe the results.

Then replace the algorithm name with another listed by the runtime. Explain why the same seed does not have to produce the same sequence when changing algorithms.

### Exercise 5 — Reproducing Parallel Tasks

Create a root SplittableRandom, call split() sequentially twice to create generators for task A and B. Run both tasks in parallel, storing results by task ID. Repeat with the same seed and split structure, comparing results per task.

Explain why sharing one root SplittableRandom between two threads to call split() concurrently is not a safe design.

### Exercise 6 — Spotting Unsuitable Generators

For the following goals, pick the suitable API and explain:

1. Replayable queue simulation.
2. Generating password reset tokens.
3. Running multiple independent simulation tasks across threads.
4. Generating fast random numbers for tasks that do not need replayable seeds.

**Guidance:** Random or an explicitly chosen algorithm generator for simulation; SecureRandom for tokens; SplittableRandom with controlled splitting for independent tasks; ThreadLocalRandom for general multithreaded access without replay.

## 15. Common Misconceptions

| Misconception | Reality |
|---|---|
| Same seed means every PRNG produces the same sequence | Sequence depends on both algorithm and seed |
| Saving the seed is enough for replay | Order, method types, parameters, data, and execution config are also needed |
| Adding one random call for debugging won't affect results | It can advance state and shift every subsequent result |
| Random is thread-safe, so sharing across threads is reproducible | Data safety does not mean the order tasks receive numbers is fixed |
| SplittableRandom can be shared across threads | The class is not thread-safe; split separate generators |
| ThreadLocalRandom can be seeded like Random | The API does not allow arbitrary seed control; setSeed is unsupported |
| SecureRandom is the best PRNG for experiments | It is for security, not replaying simulation sequences |
| Math.random() allows replay if runtime timestamp is known | The API does not accept seeds; manage generators explicitly |
| Fixed seeds provide cryptographic randomness | Known seed and algorithm make sequences predictable |
| If parallel tasks finish in different order, numbers must differ | If each task has its own generator and results map to task ID, completion order need not affect sequences |

## 16. Official Java 17 Documentation

- [Java SE 17 API — Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): LCG algorithm, seed, and reproducible sequence contract.
- [Java SE 17 API — SplittableRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): seed, split, and thread-safety limits.
- [Java SE 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): common interface for generators in Java 17.
- [Java SE 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): selecting and instantiating generators by algorithm name.
- [Java SE 17 API — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): thread-bound generator and seeding restrictions.
- [Java SE 17 API — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): generator for security purposes.
- [JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): adds the RandomGenerator API and new algorithms starting in Java 17.

**Takeaway:** To reproduce an experiment, save and stabilize **algorithm + seed + call order + parameters + input data**. In parallel processing, assign separate generators per task using stable split/seed rules. Fixed seeds enable replaying pseudo-random sequences; they do not provide security and do not guarantee full application reproducibility if logic, execution order, or environment changes.
