# Reproducible Simulations with RandomGenerator in Java 17

## 1. Why Must Simulations Be Reproducible?

Simulations often use random numbers to represent uncertain factors: customer arrival times, service durations, purchase demand, equipment failures, experimental outcomes, or point coordinates in space. One run produces one scenario; another run can produce a different scenario.

In software development, being able to **reproduce an exact run** is critical:

- When a simulation produces an anomalous result, the development team needs to replay the exact scenario to find the root cause.
- When modifying an algorithm, you need to compare the old and new versions on the same random inputs.
- When running benchmarks, you need to isolate the impact of code changes from fluctuations in input data.
- When splitting a simulation across multiple parallel tasks, you need to know which random sequence each task consumes.
- When saving research findings or reports, you must record enough information for others to replicate the experiment.

A pseudorandom number generator (PRNG) has internal state and a deterministic algorithm. If you create a generator with the same algorithm, the same seed, and invoke its methods in the exact same order, the program can reproduce the exact same sequence of results.

Java 17 provides a new API in the `java.util.random` package, centered around the `RandomGenerator` interface. This API lets you write simulations decoupled from any concrete generator class while selecting algorithms via `RandomGeneratorFactory`.

## 2. RandomGenerator in Java 17

### 2.1. A Unified Interface for Multiple Generators

`RandomGenerator` is an interface describing operations for generating random values. Many built-in Java classes implement this interface, including:

| Generator | Characteristics |
|---|---|
| `java.util.Random` | Legacy generator with a well-defined sequence contract based on seed. |
| `java.util.SplittableRandom` | Suitable for computational tasks needing to split generators per branch or task. |
| LXM generators | Family of modern algorithms provided through `RandomGeneratorFactory`. |
| `java.util.concurrent.ThreadLocalRandom` | Thread-bound generator useful for concurrent computing, though not suitable as a reproducible seeded source in the standard way. |
| `java.security.SecureRandom` | Designed for cryptographic security; not the default choice for scientific simulations or benchmarks. |

Instead of writing methods that only accept `Random`, accept `RandomGenerator` when the code only needs general generation operations:

~~~java
static double estimateSomething(RandomGenerator random) {
    return random.nextDouble();
}
~~~

As a result, the same simulation algorithm can run with `Random`, `SplittableRandom`, or an LXM generator without changing simulation logic.

### 2.2. Commonly Used Methods

| Method | Range or distribution |
|---|---|
| `nextBoolean()` | Random boolean. |
| `nextInt()` | 32-bit integer. |
| `nextInt(bound)` | Integer from `0` (inclusive) to `bound` (exclusive). |
| `nextInt(origin, bound)` | Integer from `origin` (inclusive) to `bound` (exclusive). |
| `nextLong()` | 64-bit integer. |
| `nextLong(bound)` | Long from `0` (inclusive) to `bound` (exclusive). |
| `nextDouble()` | Floating-point value in `[0, 1)`. |
| `nextDouble(origin, bound)` | Floating-point value in `[origin, bound)`. |
| `nextGaussian()` | Normally distributed value with mean `0` and standard deviation `1`. |
| `nextGaussian(mean, stddev)` | Normally distributed value with the specified mean and standard deviation. |
| `nextExponential()` | Exponentially distributed value with mean `1`. |

Bounded methods help avoid hand-written modulo or offset arithmetic that introduces bias. For example, use `nextInt(10, 21)` to generate integers from 10 through 20.

### 2.3. Selecting a Generator via RandomGeneratorFactory

`RandomGeneratorFactory` looks up and instantiates generators by algorithm name:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

String algorithm = "L64X128MixRandom";
long seed = 20250317L;

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of(algorithm);

RandomGenerator random = factory.create(seed);

System.out.println(random.nextInt());
System.out.println(random.nextDouble());
~~~

The algorithm name is part of the simulation configuration. When results must be reproducible, save both the algorithm name and the seed; saving only the seed is insufficient if a subsequent run selects a different generator.

You can list the factories provided by the runtime:

~~~java
RandomGeneratorFactory.all()
        .sorted((left, right) -> left.name().compareTo(right.name()))
        .forEach(factory -> System.out.printf(
                "%s | group=%s | stateBits=%d | splittable=%s%n",
                factory.name(),
                factory.group(),
                factory.stateBits(),
                factory.isSplittable()));
~~~

The list of algorithms depends on the running JDK/runtime. Use `RandomGeneratorFactory.all()` or `factory.name()` to inspect available algorithms rather than assuming every vendor ships the exact same set.

### 2.4. Do Not Rely on the Default Generator

`RandomGenerator.getDefault()` returns the runtime's default generator. This is convenient when an application does not need algorithm control, but it is unsuitable when simulation outputs must remain reproducible over time.

If a future runtime changes its default generator choice, the same seed could yield a different sequence. When reproducibility matters, specify the algorithm name explicitly via `RandomGeneratorFactory.of(name)`.

## 3. Seeds and Reproducibility

### 3.1. A Seed Is the Starting Point of a Pseudorandom Sequence

A seed initializes the generator's internal state. With a deterministic algorithm, a fixed seed produces a repeatable sequence of numbers:

~~~java
RandomGenerator first =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(123456789L);

RandomGenerator second =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(123456789L);

System.out.println(first.nextInt() == second.nextInt());
System.out.println(first.nextDouble() == second.nextDouble());
~~~

Both generators start from the same state. Because the calls are made in the same order, both comparisons evaluate to `true`.

If you change the second generator's seed or switch algorithms, the sequences can differ.

### 3.2. Recording the Seed in Simulation Outputs

A simulation output should record enough metadata to rerun the experiment:

| Metadata | Why it is needed |
|---|---|
| Algorithm name | Identifies the PRNG algorithm. |
| Seed | Recreates the initial state. |
| JDK vendor/version/build | Identifies the runtime and implementation used. |
| Simulation version or commit | Identifies the simulation logic. |
| Input parameters | Identifies sample sizes, distributions, coefficients, and initial conditions. |
| Input data version | Ensures underlying input datasets have not changed. |
| Parallelism/stream assignment | Identifies how random streams are partitioned across tasks. |

Example metadata saved in JSON, a CSV header, or logs:

~~~text
algorithm=L64X128MixRandom
seed=20250317
jdk=17.0.x
simulation=queue-model-v3
arrivalRate=2.0
serviceRate=3.0
warmupCustomers=10000
measuredCustomers=200000
~~~

Avoid logging a generic flag like `random=true`. It gives no clue how to recreate the scenario.

### 3.3. Fixed Seeds vs. Newly Generated Seeds

During development and testing, use a fixed seed:

~~~java
long seed = 20250317L;
~~~

In a production run that needs a fresh scenario, generate a random seed once and immediately record it in logs or metadata:

~~~java
long seed = new java.security.SecureRandom().nextLong();
System.out.println("simulationSeed=" + seed);
~~~

Here `SecureRandom` is used only to pick the initial seed. The simulation generator itself remains the PRNG selected through `RandomGeneratorFactory`. If the outcome exhibits an issue, retrieve the recorded seed to replay it.

Do not use `System.nanoTime()` as a seed without recording it. An unrecorded seed destroys reproducibility.

### 3.4. The Same Seed Is Not Enough If Call Order Changes

A generator produces a sequential stream. Every method call consumes part of its state. Thus, two simulation versions can yield different outputs even with the same algorithm and seed if:

- One version adds a `nextDouble()` call for logging or debugging.
- The generation order of random variables changes.
- A conditional branch consumes a different number of random draws than before.
- Loop iteration counts or input processing order changes.
- Parallel execution alters how generators are assigned to tasks.

Treat the consumption order of the random stream as part of the experiment configuration.

### 3.5. Reproducibility Across JDK Versions

The `RandomGenerator` API lets you select an algorithm, but you should not automatically assume every algorithm makes the exact same bit-for-bit cross-version guarantee as `java.util.Random` across all future releases and vendors. For results archived long-term:

- Record the exact algorithm name.
- Record the JDK vendor, version, and build.
- Retain the configuration and simulation code version.
- If exact reproduction is required far into the future, consider saving the generated random inputs or saving application-managed checkpoints/state.

`java.util.Random` has a long-standing sequence compatibility contract for a given seed and call sequence. Newer generators should be used with pinned and verified runtimes when reproducibility requirements span version boundaries.

## 4. Generating Common Distributions

Simulations do not rely solely on uniform numbers. Each quantity should use a distribution matching the model.

### 4.1. Uniform Distribution over Integers

To randomly pick an index from `0` to `n - 1`:

~~~java
int index = random.nextInt(n);
~~~

To pick an integer in the range `[min, max]`:

~~~java
int value = random.nextInt(min, max + 1);
~~~

The second example is safe only if `max + 1` does not overflow and the range is valid. When working near type limits, use `long` or validate bounds beforehand.

Avoid using:

~~~java
int value = Math.abs(random.nextInt()) % n;
~~~

This has two flaws: `Math.abs(Integer.MIN_VALUE)` remains negative, and modulo arithmetic introduces bias when the source range is not divisible by `n`. Use `nextInt(bound)`.

### 4.2. Uniform Distribution over Floating-Point Numbers

`nextDouble()` returns a number in `[0, 1)`:

~~~java
double u = random.nextDouble();
double x = min + (max - min) * u;
~~~

You can call directly:

~~~java
double x = random.nextDouble(min, max);
~~~

The `max` bound is exclusive. When building a model, define open/closed boundaries explicitly to avoid edge bias.

### 4.3. Bernoulli: Event with Probability p

For example, simulating a request failing with probability `p`:

~~~java
static boolean failed(RandomGenerator random, double probability) {
    if (!Double.isFinite(probability)
            || probability < 0.0
            || probability > 1.0) {
        throw new IllegalArgumentException(
                "probability must be in [0, 1]");
    }
    return random.nextDouble() < probability;
}
~~~

When `p` is 0, the event never occurs; when `p` is 1, the event always occurs. For intermediate `p`, the observed frequency approaches the expected rate only as sample size grows; never assert that the exact count equals `p` times the sample size on every run.

### 4.4. Normal Distribution

Use `nextGaussian(mean, stddev)`:

~~~java
double temperature = random.nextGaussian(25.0, 2.5);
~~~

Values follow a normal distribution with mean 25 and standard deviation 2.5. The normal distribution is unbounded; if the real-world quantity cannot be negative or exceed a threshold, choose a more suitable model or apply a statistically sound transformation.

### 4.5. Exponential Distribution

`nextExponential()` generates values from an exponential distribution with mean 1. If events occur at an average rate λ per unit time, inter-arrival times can be modeled as:

~~~java
double interArrivalTime = random.nextExponential() / lambda;
~~~

The expected value is `1 / λ`. The rate parameter `λ` must be positive and finite. The exponential distribution is commonly used to model inter-arrival times in a Poisson process or service times in a simple M/M/1 queue.

### 4.6. Weighted Element Selection

Suppose there are three request types with weights 0.6, 0.3, and 0.1. You can use cumulative weights:

~~~java
static int chooseWeighted(
        RandomGenerator random, double[] weights) {

    double total = 0.0;
    for (double weight : weights) {
        if (!Double.isFinite(weight) || weight < 0.0) {
            throw new IllegalArgumentException(
                    "weights must be finite and non-negative");
        }
        total += weight;
    }
    if (!(total > 0.0) || !Double.isFinite(total)) {
        throw new IllegalArgumentException(
                "sum of weights must be positive and finite");
    }

    double target = random.nextDouble() * total;
    double cumulative = 0.0;
    for (int i = 0; i < weights.length; i++) {
        cumulative += weights[i];
        if (target < cumulative) {
            return i;
        }
    }
    return weights.length - 1;
}
~~~

Weights do not have to sum to 1; the function normalizes by total weight. An element with weight 0 will not be selected if the total is valid.

## 5. Monte Carlo Example: Estimating Pi

Monte Carlo methods use random sampling to estimate a quantity. We sample points uniformly inside the square `[-1, 1] × [-1, 1]`. The fraction of points falling inside the unit circle approximates the area of the circle divided by the area of the square:

~~~text
N_inside / N_total ≈ π / 4
π ≈ 4 * N_inside / N_total
~~~

Java code:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public final class PiSimulation {
    private PiSimulation() {
    }

    record Result(
            String algorithm,
            long seed,
            long samples,
            long inside,
            double estimate) {
    }

    static Result estimate(long seed, long samples) {
        if (samples <= 0) {
            throw new IllegalArgumentException(
                    "samples must be positive");
        }

        String algorithm = "L64X128MixRandom";
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of(algorithm);
        RandomGenerator random = factory.create(seed);

        long inside = 0;
        for (long i = 0; i < samples; i++) {
            double x = random.nextDouble(-1.0, 1.0);
            double y = random.nextDouble(-1.0, 1.0);
            if (x * x + y * y <= 1.0) {
                inside++;
            }
        }

        double estimate = 4.0 * inside / samples;
        return new Result(
                algorithm, seed, samples, inside, estimate);
    }

    public static void main(String[] args) {
        long seed = 20250317L;
        long samples = 1_000_000L;

        Result result = estimate(seed, samples);
        System.out.println("algorithm=" + result.algorithm());
        System.out.println("seed=" + result.seed());
        System.out.println("samples=" + result.samples());
        System.out.println("inside=" + result.inside());
        System.out.println("piEstimate=" + result.estimate());
    }
}
~~~

Compile and run with JDK 17:

~~~text
javac --release 17 -encoding UTF-8 PiSimulation.java
java PiSimulation
~~~

Rerunning the same program with the same seed and sample count reproduces the exact same result within the same algorithm/runtime environment. Changing the seed produces a different sampling run. Increasing the sample count generally reduces statistical error, though it does not guarantee every single run gets monotonically closer to π.

### 5.1. Why Also Save the Sample Count?

The seed determines the initial PRNG sequence, while the sample count determines how many elements of that sequence are consumed. Two runs with the same seed where one uses 100,000 samples and the other uses 1,000,000 samples will yield different results.

When saving results, record the seed, algorithm, and sample count. If warm-up or initial sample discarding is used, save those parameters as well.

## 6. Example: M/M/1 Queue Simulation

A more practical example simulates a single-server queue:

- Customers arrive according to a Poisson process at rate λ customers per unit time.
- Service times follow an exponential distribution with rate μ.
- There is only one server.
- If the server is busy, customers wait in the queue.

For the queue to be theoretically stable, `λ < μ` is required. In an M/M/1 model, the steady-state theoretical mean waiting time and mean time in system are:

~~~text
Wq = λ / (μ * (μ - λ))
W  = 1 / (μ - λ)
~~~

The simulation should not start measuring from the very first customer because the system begins empty. We run a warm-up number of customers to bring the queue near steady state before collecting statistics.

~~~java
import java.util.random.RandomGenerator;
import java.util.SplittableRandom;

public final class QueueSimulation {
    private QueueSimulation() {
    }

    record Result(
            long customers,
            double averageWait,
            double averageTimeInSystem) {
    }

    static Result simulate(
            RandomGenerator arrivals,
            RandomGenerator services,
            long warmupCustomers,
            long measuredCustomers,
            double arrivalRate,
            double serviceRate) {

        if (warmupCustomers < 0 || measuredCustomers <= 0) {
            throw new IllegalArgumentException(
                    "invalid customer counts");
        }
        if (!Double.isFinite(arrivalRate)
                || !Double.isFinite(serviceRate)
                || arrivalRate <= 0.0
                || serviceRate <= arrivalRate) {
            throw new IllegalArgumentException(
                    "require 0 < arrivalRate < serviceRate");
        }

        long totalCustomers =
                Math.addExact(warmupCustomers, measuredCustomers);
        double arrivalTime = 0.0;
        double serverAvailableAt = 0.0;
        double totalWait = 0.0;
        double totalTimeInSystem = 0.0;

        for (long i = 0; i < totalCustomers; i++) {
            arrivalTime += arrivals.nextExponential() / arrivalRate;
            double serviceTime =
                    services.nextExponential() / serviceRate;

            double serviceStartsAt =
                    Math.max(arrivalTime, serverAvailableAt);
            double departsAt = serviceStartsAt + serviceTime;

            if (i >= warmupCustomers) {
                totalWait += serviceStartsAt - arrivalTime;
                totalTimeInSystem += departsAt - arrivalTime;
            }

            serverAvailableAt = departsAt;
        }

        return new Result(
                measuredCustomers,
                totalWait / measuredCustomers,
                totalTimeInSystem / measuredCustomers);
    }

    public static void main(String[] args) {
        long seed = 987654321L;

        // Two separate streams isolate arrival and service sequences.
        SplittableRandom root = new SplittableRandom(seed);
        RandomGenerator arrivalRandom = root.split();
        RandomGenerator serviceRandom = root.split();

        double lambda = 2.0;
        double mu = 3.0;

        Result result = simulate(
                arrivalRandom,
                serviceRandom,
                10_000,
                200_000,
                lambda,
                mu);

        double theoreticalWait =
                lambda / (mu * (mu - lambda));
        double theoreticalSystemTime =
                1.0 / (mu - lambda);

        System.out.println("seed=" + seed);
        System.out.println("customers=" + result.customers());
        System.out.println("averageWait=" + result.averageWait());
        System.out.println("theoreticalWait=" + theoreticalWait);
        System.out.println("averageTimeInSystem="
                + result.averageTimeInSystem());
        System.out.println("theoreticalTimeInSystem="
                + theoreticalSystemTime);
    }
}
~~~

Two child generators are split in a fixed order from the root `SplittableRandom`. One stream generates arrival times, and the other generates service times. This separates the two sources of randomness: if you change how many samples are drawn for arrivals, the service time stream does not shift.

With the same seed, split order, customer counts, and parameters, the simulation is reproducible. Empirical results approach the theoretical formulas only when sample sizes are sufficiently large; small deviations are normal.

## 7. Splitting Generators for Parallel Simulations

### 7.1. Why Should You Not Share One Generator Arbitrarily Across Threads?

A generator mutates its state on every call. If multiple threads access the same generator concurrently:

- Call order can depend on thread scheduling.
- The subsequence consumed by each task can vary across runs.
- Many generators are not designed for concurrent sharing.
- Synchronization or contention overhead can degrade performance.

For parallel simulations, create a dedicated generator per task or per replication. When each task has its own stream, thread scheduling no longer determines which task consumes the next random number from another task's sequence.

### 7.2. SplittableGenerator

`RandomGenerator.SplittableGenerator` is the subinterface for generators that can split into independent child generators:

~~~java
SplittableRandom root = new SplittableRandom(12345L);

RandomGenerator firstTask = root.split();
RandomGenerator secondTask = root.split();
~~~

Each `split()` call produces a child generator with its own stream. This fits distributing streams across independent tasks, especially when using parallel streams or executors.

Not every `RandomGenerator` is splittable. You can check this capability via `RandomGeneratorFactory.isSplittable()` before casting to `SplittableGenerator`.

### 7.3. Assign Streams by Task ID, Not by Thread

A common mistake is creating a new generator inside each thread with a seed dependent on thread creation order. Thread scheduling can vary, making simulation results non-reproducible.

Assign generators to **logical task IDs** before submitting tasks to an executor:

1. Create the root generator with the recorded seed.
2. Split child generators in a fixed replication order.
3. Bind child generator `i` to replication `i`.
4. Run replications on the executor or parallel stream.
5. Store results by task ID, then aggregate in a fixed order.

### 7.4. Example: Running Reproducible Parallel Replications

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.SplittableRandom;
import java.util.random.RandomGenerator;
import java.util.stream.IntStream;

public final class ParallelMonteCarlo {
    private ParallelMonteCarlo() {
    }

    static long countInside(
            RandomGenerator random, long samples) {
        long inside = 0;
        for (long i = 0; i < samples; i++) {
            double x = random.nextDouble(-1.0, 1.0);
            double y = random.nextDouble(-1.0, 1.0);
            if (x * x + y * y <= 1.0) {
                inside++;
            }
        }
        return inside;
    }

    public static void main(String[] args) {
        long seed = 445566L;
        int replications = 8;
        long samplesPerReplication = 500_000L;

        SplittableRandom root = new SplittableRandom(seed);
        List<RandomGenerator> streams =
                new ArrayList<>(replications);

        // Create streams sequentially before running in parallel.
        for (int i = 0; i < replications; i++) {
            streams.add(root.split());
        }

        long[] counts = new long[replications];
        IntStream.range(0, replications).parallel().forEach(index -> {
            counts[index] = countInside(
                    streams.get(index), samplesPerReplication);
        });

        // Aggregate sequentially in a fixed index order.
        long totalInside = 0;
        long totalSamples = 0;
        for (int i = 0; i < replications; i++) {
            totalInside += counts[i];
            totalSamples += samplesPerReplication;
        }

        double pi = 4.0 * totalInside / totalSamples;
        System.out.println("seed=" + seed);
        System.out.println("replications=" + replications);
        System.out.println("piEstimate=" + pi);
    }
}
~~~

Each replication writes only to its own slot in `counts`; results are aggregated after the parallel stream finishes. Pre-creating streams and indexing them deterministically prevents results from depending on which thread picks up which task.

For integers in this example, summing in different orders yields the same result provided there is no overflow. For floating-point sums, summation order can change the lowest bits due to floating-point rounding. Store each replication's output and sum sequentially when strict reproducibility is required.

### 7.5. Conditional Parallel Reproducibility

Splitting generators stabilizes per-task random streams, but you must still keep fixed:

- Number of replications.
- Stream creation/split order.
- Mapping from task ID to stream.
- Sample count per replication.
- Root algorithm and seed.
- Result aggregation order.

If you change the worker thread count while preserving task ID → stream mapping and per-task logic, each replication's result can remain identical. If you create streams per worker thread or alter batch partitioning, results can diverge.

## 8. Jumpable and Leapable Generators

In addition to splittable generators, Java 17 defines other stream-control capabilities via subinterfaces:

- `RandomGenerator.JumpableGenerator` supports jumping forward in the state sequence.
- `RandomGenerator.LeapableGenerator` supports larger leaps, useful for partitioning streams.
- `RandomGenerator.ArbitrarilyJumpableGenerator` supports jumps of API-specified distances.

These capabilities serve different stream-partitioning strategies. They are not mandatory for every simulation. If a simulation only needs a single sequential stream, `RandomGenerator` suffices. When running in parallel, `SplittableGenerator` is often easier to apply for per-task substreams.

Before using them, inspect the factory's capabilities:

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

System.out.println("splittable=" + factory.isSplittable());
System.out.println("jumpable=" + factory.isJumpable());
System.out.println("leapable=" + factory.isLeapable());
~~~

Do not cast a generator to a subinterface unless the factory confirms that capability. An algorithm may support splitting without supporting jumping, or vice versa.

## 9. Testing Reproducible Simulations

Simulation tests should verify both determinism and statistical plausibility.

### 9.1. Reproducibility Tests

With the same algorithm, seed, parameters, and call order, run the simulation twice and compare the results:

~~~java
Result first = estimate(20250317L, 100_000L);
Result second = estimate(20250317L, 100_000L);

if (!first.equals(second)) {
    throw new AssertionError("Simulation is not reproducible");
}
~~~

If the result is a record of integer and floating-point fields computed in the exact same order, record equality checks exact equality within the same runtime.

### 9.2. Boundary and Parameter Tests

Verify:

- Negative, zero, and positive seeds are handled according to the generator's contract.
- Sample counts must be positive.
- Probabilities lie in `[0, 1]`.
- Rates and standard deviations are finite, valid, and non-negative/positive as required by the model.
- Total weights are positive and finite.
- Sample count additions do not overflow.

Never allow a simulation to proceed with `NaN` or infinite parameters only to discover meaningless outputs at the end.

### 9.3. Statistical Tests

Reproducibility tests do not prove a distribution is correct. A generator can yield the same sequence every time while the model uses the wrong distribution.

For example, with `Bernoulli(p)`, after `N` trials, the expected count and variance are:

~~~text
E[X] = Np
Var(X) = Np(1-p)
~~~

You can check that the observed rate lies within a statistically appropriate tolerance. Never assert that the observed count equals `p * N` exactly, since finite samples always exhibit variance.

For normal distributions, check that the sample mean and variance approach the target parameters for sufficiently large `N`. For exponential distributions, check that the sample mean approaches `1 / λ`. Design tolerances around sample size to avoid overly tight thresholds that cause flaky tests.

### 9.4. Do Not Hardcode a Sequence as a Universal Standard Across All Runtimes

If a test only verifies simulation logic, compare two runs with the same seed on the same runtime or check invariants. Do not hardcode a sequence of numbers from an LXM generator and assume it is fixed across every future JDK vendor and version unless the contract guarantees it.

If an application must preserve published outputs across years, pin both runtime and algorithm, or store the generated random inputs as part of the experiment inputs.

## 10. Checkpointing and Resuming a Simulation

Saving a seed lets you rerun from the beginning. It does not automatically let you resume from the middle of a simulation.

Suppose a simulation ran 10 million steps before stopping. To continue the exact stream, you could:

1. Save a checkpoint of the model state.
2. Save the seed, algorithm, and number of consumed draws.
3. Re-instantiate the generator from the same seed.
4. Replay the exact number of draws in the same order to restore the generator to its pre-checkpoint state.
5. Continue the simulation.

Replaying can be slow and fragile if code changes the call order. Some generators offer jump mechanisms or internal state, but do not assume every implementation provides a PRNG state serialization API.

An alternative design partitions the simulation into independent batches with per-batch seeds/streams keyed by batch ID. On checkpoint, you simply save completed batch results and metadata to rerun unfinished batches. This is often far easier to operate for distributed Monte Carlo workloads.

## 11. Common Mistakes

| Mistake | Why it causes problems | Resolution |
|---|---|---|
| Saving only the seed | Different algorithms generate different sequences. | Save both algorithm name and runtime info. |
| Using the default generator | The default selection can change across releases. | Select a named generator via factory. |
| Using `Math.random()` | Hard to control generator and seed in simulation design. | Pass `RandomGenerator` into simulation functions. |
| Using `ThreadLocalRandom` for reproducible scenarios | Lacks per-task seed/stream workflow needed by simulations. | Use explicitly seeded generators or splittable streams. |
| Sharing one generator across threads | Consumption order depends on thread scheduling. | Separate generators per logical task. |
| Seeding tasks from thread ID | Thread assignment can vary between runs. | Assign streams by fixed replication/task ID. |
| Using `% bound` | Can introduce modulo bias. | Use `nextInt(bound)` or `nextLong(bound)`. |
| Adding extra random calls for logging | Shifts the rest of the random sequence. | Never share a stream with logging; log generated values or use a separate stream. |
| Testing only identical-seed equality | Does not prove distribution or model correctness. | Combine deterministic, invariant, and statistical tests. |
| Summing parallel floating-point totals in completion order | Floating-point addition order can alter low bits. | Store per-task results and aggregate in a fixed order. |
| Treating a seed as a checkpoint | A seed only reproduces from the start. | Persist model state and replay, or split into independent batches. |
| Using simulation PRNGs for security | Simulation PRNGs are not unpredictable. | Use `SecureRandom` for tokens/secrets; keep separate from simulations. |

## 12. Workflow for Building a Reproducible Simulation

A workflow you can apply in projects:

1. **Specify the model.** Define state, input variables, distributions, and stopping criteria.
2. **Choose the generator.** Select a named algorithm; if running in parallel, check splittability.
3. **Manage the seed.** Accept a seed from config or generate one once and record it.
4. **Inject RandomGenerator.** Pass the generator into simulation functions instead of creating hidden generators deep in classes.
5. **Separate streams by source or task.** Use distinct generators for arrivals, services, replications, or logical tasks.
6. **Persist metadata.** Record algorithm, seed, JDK build, model version, input data, and simulation parameters.
7. **Test reproducibility.** Rerun with identical configuration and verify identical outputs in the pinned environment.
8. **Test statistics.** Verify distributions, expected values, variances, and invariants.
9. **Measure performance.** Compare throughput and generator cost on representative workloads.
10. **Save checkpoints or batches.** Design resumption so it does not rely solely on a single initial seed.

## 13. Choosing a Generator by Goal

| Goal | Suitable choice |
|---|---|
| Need a generic API for simulation code | Accept `RandomGenerator` in methods. |
| Need an explicit algorithm and seed | `RandomGeneratorFactory.of(name).create(seed)`. |
| Need a generator easily split for parallel tasks | `SplittableRandom` or a factory with `isSplittable() == true`. |
| Need an algorithm with a long-standing sequence contract | `java.util.Random` when its sequence-compatibility contract matters more than newer features. |
| Need random numbers for security | `SecureRandom`, never a standard simulation generator. |
| Only need convenience without reproducibility | The default generator may suffice, though not for repeatable experiments. |

No single algorithm is best for every simulation. Weigh statistical quality, speed, split/jump support, compatibility requirements, and runtime implementation.

## 14. Practice Exercises

### Exercise 1 — Reproducing Monte Carlo

Run `PiSimulation` twice with the same seed and sample count. Compare the entire result record. Then change the seed and observe how the output changes.

### Exercise 2 — Choosing an Algorithm with Factory

Use `RandomGeneratorFactory.all()` to print generator names, algorithm groups, state bits, and splittability. Pick an LXM generator available in JDK 17, create two instances with the same seed, and compare their sequences.

### Exercise 3 — Bernoulli Simulation

Simulate 100,000 requests with failure probability 0.02. Record the seed, request count, and failed request count. Rerun with the same seed and verify the result. Then check whether the failure rate falls within a reasonable statistical interval.

### Exercise 4 — Queue Simulation

Run `QueueSimulation` with λ = 2 and μ = 3. Compare the average wait time with the theoretical M/M/1 formula. Vary warm-up and measured customer counts to observe the effect of sample size.

### Exercise 5 — Splitting Streams

Create a root `SplittableRandom` and split two generators for arrivals and services. Add an extra draw on the arrivals stream. Check whether the service sequence changes.

### Exercise 6 — Parallel Replications

Use `ParallelMonteCarlo` to run 8 parallel replications. Rerun with the same seed and compare each replication. Then change the executor worker count while keeping the replication count and stream mapping fixed.

### Exercise 7 — Checking Modulo Bias

Implement two ways to pick an integer in `[0, 6]`: using `nextInt(7)` and using `Math.abs(nextInt()) % 7`. Run a large sample, compare frequencies, and explain why modulo arithmetic can introduce bias.

### Exercise 8 — Designing Metadata

Create a metadata file for a simulation run containing algorithm, seed, JDK build, model version, distribution parameters, sample count, and replication count. Write a program that reads the metadata and reruns the exact configuration.

## 15. Principles to Remember

- `RandomGenerator` is the common abstraction for PRNGs in Java 17.
- Use `RandomGeneratorFactory` to select a generator by name and instantiate it with a specific seed.
- Do not rely on `RandomGenerator.getDefault()` if long-term reproducibility is required.
- The same algorithm, seed, call order, and parameters produce a reproducible pseudorandom sequence.
- Record algorithm, seed, JDK build, model version, input data, and simulation parameters.
- Use `nextInt(bound)` and `nextDouble(origin, bound)` instead of manual modulo arithmetic.
- Match distributions to the model: Bernoulli, uniform, Gaussian, exponential, or weighted categorical.
- Use `SplittableGenerator` to assign streams by logical task; never assign streams by thread ID or scheduling order.
- Create parallel streams in a fixed order and aggregate results in a deterministic order.
- Seeds let you restart from the beginning; mid-run checkpoints require saving model state and an appropriate PRNG recovery mechanism.
- Reproducibility does not replace statistical testing; verify both determinism and distributional validity.
- Simulation PRNGs are not cryptographically secure; use `SecureRandom` for secrets and tokens.

### References

- [Java SE 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html).
- [Java SE 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html).
- [Java SE 17 API — RandomGenerator.SplittableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.SplittableGenerator.html).
- [Java SE 17 API — SplittableRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html).
- [JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356).
