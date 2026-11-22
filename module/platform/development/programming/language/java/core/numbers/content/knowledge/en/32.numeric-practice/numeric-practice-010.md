# Reproducible Seeded Random Simulation in Java

## 1. Practice Scenario and Objectives

Suppose we simulate rolling dice, generating test data, or estimating π using the Monte Carlo method. We want randomness to explore many scenarios, yet when a bug appears, we need to **replay the exact random values used** in order to reproduce and diagnose it.

That is the goal of **reproducible seeded simulation**. A seed is the initial state or starting input for a *pseudorandom number generator (PRNG)*. Given the same algorithm, same seed, same sequence of calls, and same relevant execution conditions, we can regenerate the exact same output sequence.

Simple example:

```java
Random first = new Random(2026L);
Random again = new Random(2026L);

System.out.println(first.nextInt(100) == again.nextInt(100)); // true
```

This is not "true randomness" from the environment; the output sequence is computed by a deterministic algorithm. A seed lets you turn an otherwise hard-to-reproduce test case into **a replayable one**.

Lesson objectives:
- Know how to use `java.util.Random`, `SplittableRandom`, and appropriate Java 17 APIs to control seeds.
- Understand why **the same seed is not enough** to produce the same result when call patterns or distributions differ.
- Build a Monte Carlo simulation estimating π and a dice-rolling example.
- Verify reproducibility, compare multiple seeds, and avoid confusing reproducibility with statistical correctness.
- Know how to record the seed, step counts, algorithm version, parameters, and parallelism strategy to reproduce bugs when they happen.
- Distinguish PRNGs for simulation from cryptographically secure random generators.

## 2. How Do Seeds, PRNGs, and State Change?

A PRNG maintains **internal state**. Each time a generation method is called, it uses the current state to compute a result and updates the state for the next call.

Conceptual model:

```text
                 fixed seed
                     |
                     v
              initialize PRNG
                     |
                 state S0
                     |
            nextInt / nextDouble
                     v
          output R0, state S1
                     |
            nextInt / nextDouble
                     v
          output R1, state S2
                     |
                    ...
```

If two independent PRNGs start from the same seed and execute the **same sequence of methods with the same arguments**, they produce the same results under their deterministic algorithm. Conversely, if run A calls `nextInt()` three times while run B makes one extra call in between, the values paired with each business step can diverge despite the same seed.

There is **no guarantee** that "the same seed" yields the same sequence if you switch from `Random` to `SplittableRandom`, change algorithms, change call order, change thread partitioning, or alter a component that consumes the RNG.

A seed **does not determine the statistical accuracy** of a simulation: it determines the starting point of a pseudorandom sequence. The result from one seed may be close to the theoretical value or deviate significantly, especially when sample counts are small.

## 3. Choosing the Right API in Java

| API | How seed is used | Suitable scope | Notes |
| --- | --- | --- | --- |
| `java.util.Random` | `new Random(longSeed)` | Examples, tests, and sequential simulations | Core algorithm and state update are documented by Java; methods produce repeatable sequences for identical seed/call sequence |
| `java.util.SplittableRandom` | `new SplittableRandom(longSeed)` | Multi-threaded simulations / needing child generators | Provides `split()` to spawn child generators; do not share one instance across threads without an appropriate strategy |
| `java.util.random.RandomGenerator` (Java 17+) | Common interface; select appropriate implementation | Designing APIs decoupled from a concrete class | Must record **algorithm/implementation name**, not just the seed |
| `java.util.random.RandomGeneratorFactory` (Java 17+) | Select named algorithm, create generator from seed | Experiments requiring algorithm management | Do not assume two different algorithms yield the same results |
| `ThreadLocalRandom` | Does not allow applications to set a seed via `setSeed` | Convenient per-thread generation when replay via controlled seed is unnecessary | Not suitable when a specific seed is required |
| `SecureRandom` | Designed for security needs, not a standard simulation PRNG | Tokens, keys, nonces, and cryptographic uses | Never use a fixed public seed to generate secret data |

**Practical choice:** For sequential simulations and simple reproducibility tests, `Random` with an explicitly recorded seed is usually easy to follow. For simulations with multiple independent branches, `SplittableRandom` supports splitting generators, while still requiring control over **split order**, each branch's workload, and runtime configuration.

### Creating Random from a seed

```java
long seed = 2026L;
Random rng = new Random(seed);

int die = rng.nextInt(6) + 1; // 1..6, including 1 and 6
double u = rng.nextDouble(); // [0.0, 1.0)
```

`Random.nextInt(6)` generates integers from 0 to 5 uniformly per the API contract; adding 1 simulates a six-sided die. The upper bound 6 is **exclusive**.

With Java 17's `SplittableRandom`, you can call:

```java
SplittableRandom rng = new SplittableRandom(2026L);
int die = rng.nextInt(1, 7);           // 1..6
double x = rng.nextDouble(-1.0, 1.0); // [-1.0, 1.0)
```

The statements above are illustrative snippets used inside a method, requiring the corresponding imports.

## 4. Reproducibility Principle: Same Seed + Same Operations + Same Context

There are three common levels:

**Level A — Replaying the exact sequence on a sequential generator.** Keep seed, algorithm, and calls identical. For instance, calling `nextInt(6)` eight times on `Random(2026L)` produces the same eight-element sequence.

**Level B — Replaying a simulation.** Beyond the generator, keep input data, iteration counts, rules mapping random numbers to events, rounding, operation order, and conditional branches identical. A small change, such as adding an RNG call to simulate weather, can make all subsequent turns differ.

**Level C — Replaying across environments/versions or multiple threads.** You must also control the implementation, algorithm name, program/JDK version if relying on implementation details, thread partitioning, thread count, result-merging order, and floating-point policies.

A common design bug:

```java
Random rng = new Random(2026L);
int first = rng.nextInt(100);
int second = rng.nextInt(100);

// In another run, code makes an extra rng.nextInt(100) call before computing second.
// The value assigned to "second" will no longer match.
```

**Reproducibility of the RNG source** does not guarantee **reproducibility of the whole system** if the application has I/O, wall-clock time, external data, race conditions, or non-deterministic algorithms.

## 5. Practice 1: Rolling Dice and Replaying Results

Create a function taking a seed and roll count. Do not pass a shared external generator into cases you want completely isolated; create a fresh generator from the seed for each replay:

```java
static int[] rollDice(long seed, int rolls) {
    if (rolls < 0) {
        throw new IllegalArgumentException("rolls must be >= 0");
    }
    Random generator = new Random(seed);
    int[] result = new int[rolls];
    for (int i = 0; i < rolls; i++) {
        result[i] = generator.nextInt(6) + 1;
    }
    return result;
}
```

This is a **method** to place inside a Java class, with `import java.util.Random;`. Each new call with the same `seed` and `rolls` performs the same number of `nextInt(6)` calls in the same order.

```java
int[] a = rollDice(2026L, 8);
int[] b = rollDice(2026L, 8);

System.out.println(Arrays.equals(a, b)); // true
```

Import `java.util.Arrays` when using `Arrays.equals`. Changing the seed to 2027L may generate a different sequence. Do not hard-assert that **two different seeds always** produce different result arrays: finite outputs can collide by chance, especially with small sample counts or small value domains.

### Why not recreate Random on every roll?

The following code produces less variety than intended:

```java
for (int i = 0; i < 8; i++) {
    Random rng = new Random(2026L); // Resets the same seed on every iteration!
    int die = rng.nextInt(6) + 1;
    // die repeats the very same first value of the generator.
}
```

If you want eight consecutive rolls, **create one generator before the loop** and call it eight times. If you want eight independent scenarios, use eight separately managed seeds rather than merely "repeating the same seed" for every scenario.

## 6. Practice 2: Monte Carlo Simulation Estimating π

A point `(x, y)` is generated uniformly in the square `[-1,1) × [-1,1)`. The point lies inside the unit circle when:

```text
x² + y² <= 1
```

The area ratio of the circle to the square is `π / 4`. If we generate `N` uniform points and count `inside` points falling inside the circle, we compute:

```text
piEstimate = 4 × inside / N
```

As `N` grows, sampling error generally decreases statistically; however, **a fixed seed does not turn the estimate into the exact value of π**, and does not guarantee every increase in `N` improves the result.

### Safe, replayable implementation

```java
record Estimate(long inside, int trials, double pi) {}

static Estimate estimatePi(long seed, int trials) {
    if (trials <= 0) {
        throw new IllegalArgumentException("trials must be > 0");
    }
    SplittableRandom generator = new SplittableRandom(seed);
    long inside = 0;
    for (int i = 0; i < trials; i++) {
        double x = generator.nextDouble(-1.0, 1.0);
        double y = generator.nextDouble(-1.0, 1.0);
        if (x * x + y * y <= 1.0) {
            inside++;
        }
    }
    return new Estimate(inside, trials, 4.0 * inside / trials);
}
```

This is a **method and record snippet** to place in a Java 17 class/program, with `import java.util.SplittableRandom`.

Design points:
- `trials > 0` ensures no division by 0.
- A fresh `SplittableRandom(seed)` is initialized **at the start of each simulation**, avoiding receiving a generator already consumed by an earlier call.
- Each iteration makes exactly **two calls to `nextDouble(-1.0,1.0)`**, in the order x then y.
- `inside` is `long` to adapt easily if the loop is expanded; for `int trials`, this counter cannot overflow within the given range.
- `4.0 * inside / trials` is `double` arithmetic, not integer division truncating the remainder.
- When rerun with the same seed, trial count, and identical implementation/call order, the `inside`/`pi` pair is reproducible.

### Evaluating statistical quality

In this simulation, the probability of a point landing inside the circle is `p = π / 4`. Assuming independent samples per the model, the ratio `inside / N` has standard deviation approximately:

\[
\sqrt{\frac{p(1-p)}{N}}
\]

The standard deviation of `piEstimate = 4 × inside/N` is roughly four times that value. This is an estimate of **sampling error**, not a guarantee that one run must fall within a tight interval. Do not assert that the result from one specific seed must be "closer to π" than another seed's result. Multiple independent seeds, statistics, and appropriate hypothesis tests are needed to evaluate distribution quality.

## 7. Complete Java 17 Program and Verified Output

Create the file **`SeededSimulationDemo.java`**:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.Random;
import java.util.SplittableRandom;

public class SeededSimulationDemo {
    record Estimate(long inside, int trials, double pi) {}

    static int[] rollDice(long seed, int rolls) {
        if (rolls < 0) throw new IllegalArgumentException("rolls must be >= 0");
        Random generator = new Random(seed);
        int[] result = new int[rolls];
        for (int i = 0; i < rolls; i++) {
            result[i] = generator.nextInt(6) + 1;
        }
        return result;
    }

    static Estimate estimatePi(long seed, int trials) {
        if (trials <= 0) throw new IllegalArgumentException("trials must be > 0");
        SplittableRandom generator = new SplittableRandom(seed);
        long inside = 0;
        for (int i = 0; i < trials; i++) {
            double x = generator.nextDouble(-1.0, 1.0);
            double y = generator.nextDouble(-1.0, 1.0);
            if (x * x + y * y <= 1.0) inside++;
        }
        return new Estimate(inside, trials, 4.0 * inside / trials);
    }

    public static void main(String[] args) {
        long seed = 2026L;
        int[] first = rollDice(seed, 8);
        int[] replay = rollDice(seed, 8);
        int[] other = rollDice(seed + 1, 8);
        System.out.println("dice=" + Arrays.toString(first));
        System.out.println("sameSeedSameDice=" + Arrays.equals(first, replay));
        System.out.println("otherSeedDice=" + Arrays.toString(other));

        Random a = new Random(seed);
        Random b = new Random(seed);
        int a0 = a.nextInt(100);
        int a1 = a.nextInt(100);
        int b0 = b.nextInt(100);
        System.out.println("sameFirstDraw=" + (a0 == b0));
        System.out.println("differentDrawPosition=" + (a1 != b0));
        System.out.println("draws=" + a0 + "," + a1 + "," + b0);

        Estimate m1 = estimatePi(seed, 10_000);
        Estimate m2 = estimatePi(seed, 10_000);
        Estimate m3 = estimatePi(seed + 1, 10_000);
        System.out.println("sameSimulation=" + m1.equals(m2));
        System.out.println("piSeed2026=" + String.format(Locale.ROOT,
                "inside=%d,trials=%d,pi=%.6f", m1.inside(), m1.trials(), m1.pi()));
        System.out.println("piSeed2027=" + String.format(Locale.ROOT,
                "inside=%d,trials=%d,pi=%.6f", m3.inside(), m3.trials(), m3.pi()));

        SplittableRandom parent1 = new SplittableRandom(seed);
        SplittableRandom parent2 = new SplittableRandom(seed);
        int child1 = parent1.split().nextInt(1, 101);
        int child2 = parent2.split().nextInt(1, 101);
        System.out.println("reproducibleSplit=" + (child1 == child2));
        System.out.println("childDraw=" + child1);

        try {
            estimatePi(seed, 0);
            throw new AssertionError("Expected invalid trial count");
        } catch (IllegalArgumentException expected) {
            System.out.println("zeroTrialsRejected=true");
        }
    }
}
```

Compile and run (JDK 17+):

```bash
javac SeededSimulationDemo.java
java SeededSimulationDemo
```

Verified output from compiling with `javac --release 17` and running the program:

```text
dice=[6, 5, 2, 1, 4, 5, 6, 5]
sameSeedSameDice=true
otherSeedDice=[4, 1, 1, 1, 1, 6, 3, 5]
sameFirstDraw=true
differentDrawPosition=true
draws=99,50,99
sameSimulation=true
piSeed2026=inside=7850,trials=10000,pi=3.140000
piSeed2027=inside=7877,trials=10000,pi=3.150800
reproducibleSplit=true
childDraw=72
zeroTrialsRejected=true
```

**Important explanations:**

1. Both calls to `rollDice(2026L, 8)` build two independent generators with the same seed; because the procedure is identical, the arrays match.
2. `otherSeedDice` differs in this concrete example when seed = 2027L. This is observed data from the program, not a theorem that every different seed produces a different sequence.
3. `a` and `b` share the same seed: the first draw from each generator gives 99. The second draw of `a` gives 50; comparing `a1` with the first draw `b0` illustrates the effect of **position in the sequence**.
4. With 10,000 points, seed 2026L yields 7,850 points inside the circle → estimated π is 3.14; seed 2027L yields 7,877 points → 3.1508. Both results are **simulation samples**, not guaranteed accuracy for every seed.
5. Both independent `SplittableRandom` instances have the same seed and each call `split()` exactly once, so the child generators produce the same result (72) in the verified environment.
6. `estimatePi(...,0)` is rejected with `IllegalArgumentException`; this is input validation, not a random error.

## 8. Why Does the Same Seed Sometimes Still Not Give the Same Result?

### 8.1. Different call order or call count

Generation calls consume state. For example:

```java
Random x = new Random(123L);
Random y = new Random(123L);

int firstX = x.nextInt(100);
int secondX = x.nextInt(100);
int firstY = y.nextInt(100);
// firstX == firstY, but secondX does not have to equal firstY.
```

If conditional branches depend on different data, two runs may invoke the RNG a different number of times. To replay, fix both the data and **the order of events**.

### 8.2. Different generation algorithm

`Random`, `SplittableRandom`, and implementations in `java.util.random` are **different generators**. Do not compare results for seed 42 across two classes and conclude one has a bug because they do not match.

If you want to test an application contract independently of the algorithm, verify properties such as:
- die results fall within 1..6;
- identical configuration reproduces within the chosen algorithm;
- no out-of-bounds index;
- distribution exhibits proper statistical properties across many seeds (with properly designed tests).

If you want to reproduce **exact values across versions and machines**, record the algorithm name, JDK/implementation version, and sample outputs to catch changes; if requirements are strict, specify or freeze the PRNG algorithm in the application protocol rather than assuming every API guarantees bit-for-bit identity across all runtimes.

### 8.3. Different distribution parameters or methods

`nextInt(100)` and `nextInt(200)` map outputs differently. Even with the same generator and seed, changing bounds, changing `nextDouble` call counts, switching to a Gaussian distribution, or inserting `nextGaussian()` can alter the sequence of values seen by business logic. APIs may consume internal state in different numbers of steps; do not assume one method call equals one standard PRNG step.

### 8.4. Non-determinism outside the RNG

If source data arrives in varying order (e.g., reading non-deterministic events, iterating over unordered collections, changing thread counts), business logic may consume the RNG in a different order. If results are aggregated using `double` in different orders, floating-point addition can also alter trailing digits.

**A seed is necessary, but not sufficient** to control every source of non-determinism in a system.

## 9. Multiple Threads: Split Generators Instead of Arbitrary Sharing

### 9.1. Avoiding dependence on thread scheduling

Sharing one generator across multiple workers can make **which number goes to which worker** depend on execution order. `Random` supports multi-threaded use per API specs, yet that does not yield predictable results per task; `SplittableRandom` is not designed for concurrent calls on the same instance across threads.

A better approach is assigning **a dedicated generator to each work branch**, with a fixed mapping between branch ↔ seed or child generator.

### 9.2. Splitting with SplittableRandom

```java
long rootSeed = 2026L;
SplittableRandom root = new SplittableRandom(rootSeed);

SplittableRandom taskA = root.split();
SplittableRandom taskB = root.split();

// Pass each child generator to exactly one task.
int a = taskA.nextInt(100);
int b = taskB.nextInt(100);
```

The code above is an illustrative snippet inside a method. To stay reproducible:
1. Create `root` from the same seed.
2. Call `split()` in the **same deterministic order**, e.g., pre-generating a list of generators for tasks with fixed IDs.
3. Assign each child generator to its exact task; **never share** one instance across multiple tasks.
4. Keep the algorithm and call count stable within each task.
5. Collect results in a deterministic order if merging is order-dependent, especially with `double`.

If worker counts or split order change, per-task results can change even with an unchanged root seed. When task IDs must be independent of scheduling order, use a deterministic seed-derivation strategy from root seed and ID (with a properly designed/tested mixing function), or an application-managed counter/index-based generator.

### 9.3. Two different requirements: reproducibility vs. statistical independence

Two generators using **the same seed** and same algorithm produce **the same sequence**, not two independent sample streams. If you reuse the same seed to simulate 1,000 runs, you may be repeating one run 1,000 times.

To evaluate variation across runs, use distinct generation streams according to a designed plan, such as managing seeds by run ID or splitting from a root generator in a deterministic order. Do not assume simply changing the seed by `seed + i` proves streams are completely independent in all statistical properties; for sensitive simulations, consider generator quality and stream-splitting design.

## 10. Writing Tests to Verify Reproducibility

### 10.1. Byte-for-byte or value-for-value replay checks

Example with a dice array:

```java
int[] first = rollDice(2026L, 100);
int[] second = rollDice(2026L, 100);
if (!Arrays.equals(first, second)) {
    throw new AssertionError("Reproducibility violated");
}
```

In a Java 17 program, import `java.util.Arrays`. If `double` comparison requires bit-exactness, use `Double.doubleToLongBits()` or `Double.doubleToRawLongBits()` per contract, instead of comparing with an epsilon when the goal is **exact replay**. For the Monte Carlo record holding identical `inside`/`trials` and identical arithmetic, the record's `equals()` is an appropriate check in the example.

### 10.2. Validating distribution properties

Do not confuse **reproducible** with **statistically correct**. For dice, at minimum verify:

```text
For every die result in the simulation:
    1 <= die <= 6
```

To check near-uniform probability, use enough samples and proper statistical tests (e.g., a chi-squared test at a defined significance level), rather than asserting all six faces appear equally often in a short sequence.

For the π simulation:
- `inside` must lie in `[0, trials]`.
- `piEstimate` must lie in `[0,4]`.
- With the same seed, trials, and algorithm environment, results must be reproducible.
- To evaluate estimation error, run **multiple sessions with different seeds/streams** and analyze the result distribution; do not use a single seed to judge statistical accuracy.

### 10.3. Testing invalid inputs

Also test:
- negative roll count: must reject;
- zero or negative Monte Carlo trials: must reject;
- invalid bounds when calling `nextInt(bound)` or `nextDouble(origin,bound)`;
- sample counts large enough to overflow `int` or exhaust memory if designing an array storing all results;
- seeds stored as text: must parse accurately, avoiding bit loss from passing through `double` or non-lossless number formats.

Do not attempt to allocate an array of billions of elements just to prove a configuration invalid; check domain bounds and resource budgets first.

## 11. Recording Data to Replay Failures

In bug reports or experiment logs, record:

| Information | Example | Why needed |
| --- | --- | --- |
| Problem/algorithm name | Monte Carlo π | Identifies which process consumes the RNG |
| Seed | `2026` | Re-initializes the generator |
| PRNG | `SplittableRandom` | Same seed with a different algorithm produces a different sequence |
| Model and parameters | `trials = 10000`; range `[-1,1)` | Preserves step count and sample mapping |
| Program version | commit/build/version | Prevents code changes from shifting call counts |
| JDK and environment (when needed) | JDK 17, vendor | Captures runtime details affecting consistency |
| Parallelism strategy | task ID, child seed, split order | Replays the exact threads |
| Non-RNG inputs | dataset, config | Ensures no source of non-determinism is missed |
| Output/checksum | `inside = 7850` | Quick verification during replay |

Store seeds as `long` or exact decimal integer strings. Never serialize a 64-bit seed through an intermediate conversion to `double` if it can lose large-integer precision.

If running multiple simulation sessions, log **each session's own seed**, or the root seed plus the defined seed-derivation scheme. Saying only "seed 2026" is insufficient if task count and generator allocation order are unrecorded.

## 12. Designing Testable and Maintainable Simulations

A convenient pattern is passing the seed as an explicit input parameter:

```java
// Illustrative method inside a Java class.
static SimulationResult simulate(long seed, SimulationConfig config) {
    Random rng = new Random(seed);
    // Use rng solely within this simulation run.
    // The returned result contains statistics and, if needed, the seed for diagnosis.
    throw new UnsupportedOperationException("API design example");
}
```

The snippet above **only illustrates the API shape**, not a complete program (`SimulationResult` and `SimulationConfig` are application-defined types). In the standalone code above, `estimatePi(seed,trials)` is a concrete implementation of this idea.

Principles:
1. **Seed is an input**, not hidden inside `System.currentTimeMillis()` or a singleton with unknown state.
2. The generator belongs to the lifecycle of **one simulation run**; never accidentally reuse it across test cases.
3. Keep simulation functions free of I/O or external side effects where possible, making replay and comparison easy.
4. Every rule mapping PRNG outputs to domain data should be clearly defined.
5. If multi-threading is needed, manage seeds/branches before submitting tasks and log ID mappings.
6. Keep **determinism**, **validity**, and **statistical** tests separate.

For exercises or CI, fix the seed so a bug does not appear randomly today and vanish tomorrow. To uncover more bugs in production systems, you can run additional varying seeds, while **always logging any failing seed**.

## 13. Common Mistakes and How to Avoid Them

1. **Creating `new Random()` without a seed and expecting reproducibility.** Each initialization may receive a different seed; pass an explicit seed and log it.
2. **Creating `new Random(sameSeed)` inside every loop iteration.** You keep getting the first values of the same sequence; keep one generator for the entire simulation.
3. **Assuming the same seed gives the same result when switching RNGs.** The algorithm may differ; record the class/algorithm name.
4. **Adding an RNG call in a side branch without updating golden tests.** Changing consumption positions shifts all subsequent samples; control flow or design independent streams.
5. **Sharing one generator across threads and expecting each task to always get the same samples.** Scheduling can alter call order; allocate generators per task with deterministic splitting.
6. **Assuming two different seeds must produce different data.** Finite sequences can collide; never assert inequality across two seeds as a mandatory invariant.
7. **Treating one fixed seed as proof of simulation quality.** It only ensures replayability; evaluate multiple runs/samples for statistical checks.
8. **Using `SecureRandom` with a fixed seed to generate replayable tokens.** That defeats security; use `SecureRandom` properly in security contexts without exposing entropy.
9. **Failing to record version/algorithm while changing parallel execution.** A bare seed is not enough to reproduce a changed system.
10. **Failing to document sample bounds/units.** `nextInt(6)` gives 0..5, not 1..6; `nextDouble(-1,1)` excludes the upper bound.
11. **Storing all results in a huge array when only summary statistics are needed.** Compute in streaming fashion like the `inside` counter to save memory and avoid index overflow.
12. **Confusing "unpredictable randomness" with seeded PRNGs.** Simulation PRNGs are replayable, not suitable by default for cryptographic goals.

## 14. Self-Check Exercises

**Exercise 1 — replaying dice.** Why does calling `rollDice(2026L,8)` twice return the same array?  
**Answer:** each call creates a `Random` from the same seed and calls `nextInt(6)` exactly eight times, in the same order.

**Exercise 2 — two different seeds.** Can we state that two different seeds will never produce the same single die roll?  
**Answer:** no. Even with different initial states, there are only six possible outputs, so many seeds can produce the same result (or short sequence).

**Exercise 3 — shifting call position.** Two generators have the same seed, but one calls `nextInt(100)` one extra time before a critical step. Must the value at that step match?  
**Answer:** no. The two runs are drawing outputs from different positions in the sequence.

**Exercise 4 — checking π.** In a simulation of 10,000 points, 7,850 fall inside the circle. What is the π estimate?  
**Answer:** `4.0 × 7850 / 10000 = 3.14`.

**Exercise 5 — identical results do not prove quality.** If 100 runs with the same seed all yield π = 3.14, are those 100 independent samples for evaluating reliability?  
**Answer:** no. That is merely 100 replays of the exact same simulation sample.

**Exercise 6 — concurrency.** Two tasks receive child generators from the same root seed, but the order of `split()` calls is swapped in a later run. Must each task's result still match?  
**Answer:** no. The generator assigned to each task changed; branches must be assigned via deterministic order or ID.

**Exercise 7 — proper testing.** How do a reproducibility test and a statistical test differ?  
**Answer:** a reproducibility test verifies that the same seed/configuration yields the same result; a statistical test evaluates distribution properties across sufficiently many samples or independent streams.

## 15. Checklist Before Submitting a Simulation

- [ ] Simulation function explicitly accepts **seed** and sample count.
- [ ] Generator is created **once per run**, not reset on each sample.
- [ ] Random bounds follow the rules, e.g., dice 1..6 and coordinates `[-1,1)`.
- [ ] Each run controls RNG call order and validates input parameters.
- [ ] Re-running with the same seed/configuration produces identical results in the verified environment.
- [ ] At least one other seed is tested to observe variance; do not force two seeds' outputs to be strictly unequal.
- [ ] Domain invariants are checked, e.g., `0 <= inside <= trials`.
- [ ] If running in parallel, the seed/split/task-ID strategy does not depend on scheduling.
- [ ] Seed, algorithm, parameters, program version, and results are recorded in diagnostic output.
- [ ] Seeded PRNGs are not used for tokens, passwords, or secret data.

## 16. Conclusion

- **A seed enables replaying a pseudorandom sequence**, provided the algorithm, call sequence, and context remain consistent.
- With Java 17, use `Random(seed)` for simple examples; use `SplittableRandom(seed)` when a generator must be split into independent streams according to a deterministic plan.
- **The same seed does not guarantee the same whole-program output** if random consumption, data, thread counts, or algorithms change.
- Monte Carlo simulations can be tested **for reproducibility** with the same seed, while multiple seeds/samples are needed to check **statistical properties**.
- When bugs need replaying, record **seed + algorithm name + parameters + version + threading order/strategy**; do not log only a single seed number.
- Simulation PRNGs and security RNGs serve **two different goals**.

Official Java SE 17 documentation:
- [`Random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html)
- [`SplittableRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html)
- [`RandomGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html)
- [`RandomGeneratorFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html)
- [`ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html)
- [`SecureRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html)
