# Pseudorandom Numbers, Seeds, and Reproducibility Requirements in Java

## 1. Stateful PRNGs: the seed is the starting point

A **pseudorandom number generator (PRNG)** produces a seemingly random sequence using a deterministic algorithm and internal state. A seed initializes the state; after each generated value, the state typically advances to a new position:

```text
seed --> S0 --next--> r1,S1 --next--> r2,S2 --next--> r3,S3 ...
```

Three **distinct** goals when using a source of randomness:

- **Exact replay:** reproducing every exact value of a run.
- **Statistical quality:** the sequence has a distribution/correlation suitable for simulation.
- **Unpredictability:** an observer cannot feasibly compute and guess the next token, verification code, or secret data.

A generator with a fixed seed makes tests reproducible, but **is not automatically cryptographically secure**. `java.util.Random` serves general simulation; data that must resist prediction uses `java.security.SecureRandom` along with secure token management.

## 2. Why does the same seed not always yield the same business result?

```java
import java.util.Random;

Random first = new Random(42L);
Random second = new Random(42L);
int a = first.nextInt(100);   // 30
int b = first.nextInt(100);   // 63
int c = second.nextInt(100);  // 30
```

Two separate instances with the same seed produce the same sequence **if they use the same algorithm, the same calls, and the same order**. The `first` instance is already at the second position when drawing `b`, whereas `second` is only drawing its first number. If an extra draw for weather is added before rewards in a game, the number used for rewards can change even though the seed is still 42.

| Different factor | Consequence |
| --- | --- |
| Random vs. SplittableRandom algorithm | Same seed does not produce a common algorithm |
| Number/order of calls to nextInt, nextLong, nextGaussian | State may advance by a different number of steps |
| Bound/origin or a new conditional branch | Results or consumption history change |
| Threads sharing a single generator | Order in which tasks receive numbers depends on scheduler timing |
| Input or code version changes | Number of draws may no longer align |

For classic `java.util.Random`, the algorithm uses a 48-bit state, and the output sequence for the same seed and call schedule is specified. The next lesson explains `Random.setSeed` and the 48-bit details; separate lessons cover per-thread generators, splitting, and the Java 17 factory.

## 3. Exact reproducibility or statistical reproducibility?

**Exact replay** requires the values at each step to match identically. It requires the seed, algorithm name, call history, and controlled execution environment. If a job is already halfway through, the initial seed does **not** tell you what state the generator is currently in; you must replay the same history or save a checkpoint when an appropriate mechanism exists.

**Statistical reproducibility** only requires similar statistical properties or distributions across trials; individual values do not have to match. A fixed seed is useful for regression tests, but it does not prove simulation correctness across all seeds, uniformity, or resistance to prediction.

For parallel simulations, do not share a single instance and assume each task receives the same sequence across two runs: threads can draw numbers in different orders. You can use a dedicated generator per **stable task identifier**, or split generators using `split()` on a fixed splitting schedule. Different seeds do not by themselves prove that sequences are statistically independent; you must consider the algorithm and stream-management strategy.

## 4. What should you log to reproduce a bug?

For **non-secret** data, record at minimum:

1. **Class/algorithm name**, such as `java.util.Random` or `L64X128MixRandom` (Java 17).
2. **The actual seed** and initialization mechanism; if an automatically generated seed is not logged, replay is difficult.
3. **Call sequence**, such as five calls to `nextInt(100)`, bounds/origins, and the number of generator splits.
4. **Code version and input data** if they affect branching and the consumption schedule.
5. **Task→generator assignment** along with the seed-splitting rule when the workload runs in parallel.

Do not log CSPRNG seeds/state or security tokens for replay purposes like simulation seeds; that information itself may be a secret.

## 5. Runnable Java 17 example

Save as `RandomSeedReplayDemo.java`:

```java
import java.util.Arrays;
import java.util.Random;

public class RandomSeedReplayDemo {
    private static int[] samples(long seed, int count) {
        Random rng = new Random(seed);
        int[] values = new int[count];
        for (int i = 0; i < count; i++) {
            values[i] = rng.nextInt(100);
        }
        return values;
    }

    public static void main(String[] args) {
        int[] first = samples(42L, 5);
        int[] replay = samples(42L, 5);
        System.out.println(Arrays.toString(first));
        System.out.println("replay=" + Arrays.equals(first, replay));

        Random shifted = new Random(42L);
        shifted.nextInt(100);
        System.out.println("shiftedFirst=" + shifted.nextInt(100));
    }
}
```

```bash
javac --release 17 RandomSeedReplayDemo.java
java RandomSeedReplayDemo
```

```text
[30, 63, 48, 84, 70]
replay=true
shiftedFirst=63
```

This is a sequence reproducibility check, not a measurement of statistical quality or security verification.

## 6. Choosing an API by purpose

| Need | Approach |
| --- | --- |
| Sequential tests/simulations needing replay | `new Random(seed)` with a controlled call schedule |
| Multithreading without explicit seeds | `ThreadLocalRandom.current()` inside workers |
| Assigning generators to task branches | `SplittableRandom.split()` with an explicit splitting schedule |
| Configuring a Java 17 algorithm | `RandomGeneratorFactory.of(name).create(seed)` if the algorithm supports seeding |
| Generating tokens/secrets | `SecureRandom` with a data-lifecycle protection policy |

**Key takeaway:** A seed initializes a PRNG, but the final output also depends on the algorithm, call sequence, and execution conditions. Reproducibility and unpredictability are two separate goals that require choosing the right API.

**References:** [Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html), [RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html), [SplittableRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html), [SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html).
