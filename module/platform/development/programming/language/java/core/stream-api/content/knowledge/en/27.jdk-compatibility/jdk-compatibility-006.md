# Distinguishing Preview Gatherers from the Official API Since Java 24

**Stream Gatherers** extend the Java Stream API with the ability to define **custom intermediate operations**. Whereas `filter` and `map` process individual elements and `collect` aggregates at the end of a pipeline, a `Gatherer` can maintain state, create windows, emit multiple results, stop early, or transform outputs in ways that are awkward with built-in intermediate operations.

However, when learning or deploying `Stream.gather(...)`, **the JDK version is part of correctness**. Stream Gatherers appeared as a **preview API in Java 22**, entered a **second preview in Java 23**, and became an **official API in Java 24**. These three stages do not share the same compilation, execution, and compatibility guarantees.

This lesson belongs to the **JDK Compatibility** chapter of the **JAVA_STREAM_API** module. Besides distinguishing JDK milestones, we will build pipelines with `Gatherers.windowFixed`, `windowSliding`, `scan`, `fold`, and `mapConcurrent`; see how to write a custom Gatherer; determine deployment strategies for applications still running Java 17/21; and evaluate laziness, parallel processing, resources, state, and performance.

## 1. Version Map: Java 22, 23, and 24

| JDK | Stream Gatherers Status | JEP | Compiling Code Using Gatherer | Running the Program |
| --- | --- | --- | --- | --- |
| Java 8–21 | **No standard Stream Gatherers API** | — | Cannot directly use `java.util.stream.Gatherer` from this JDK | Needs an alternative or JDK upgrade |
| Java 22 | **First preview** | [JEP 461](https://openjdk.org/jeps/461) | JDK 22, enable `--enable-preview` with `--release 22` | JDK 22, enable `--enable-preview` |
| Java 23 | **Second preview** | [JEP 473](https://openjdk.org/jeps/473) | JDK 23, enable `--enable-preview` with `--release 23` | JDK 23, enable `--enable-preview` |
| Java 24 | **Official API, no longer preview** | [JEP 485](https://openjdk.org/jeps/485) | JDK 24, normal compilation | JDK 24, normal execution |
| Java 25 | **Continues as official API** | Standardized since JDK 24 | Use JDK and build config matching target | Runtime must support the APIs the app uses |

Starting in Java 24, `Stream.gather`, `Gatherer`, and `Gatherers` are an official part of the `java.base` standard library. **No `--enable-preview` flag is needed just to use Stream Gatherers on Java 24.** If a Java 24 application simultaneously uses **another preview feature**, that feature's preview requirement is a separate matter.

Three easily confused points to distinguish:

1. **"API exists"**: the JDK contains the needed classes and methods.
2. **"Calling the API is permitted"**: on JDK 22/23 preview must be enabled; on JDK 24 it does not.
3. **"Runs on another machine"**: depends on the runtime JDK version and the bytecode version compiled for the app; a newer JDK **does not automatically make an application backward-compatible with older JDKs**.

### Timeline

```text
Java 21         Java 22               Java 23               Java 24
   |               |                     |                     |
   |      JEP 461: Preview       JEP 473: Preview 2    JEP 485: Final
   |               |                     |                     |
No Gatherer   --enable-preview     --enable-preview      No flag needed
              at compile/run       at compile/run        for Gatherer
   |               |                     |                     |
   +---------------+---------------------+--------------------->
            Transition from preview to official API
```

**Scope conclusion:** Learners using **Java 17/21** can study the theory and standard Stream operations, but **cannot directly run standard `Stream.gather` examples** without moving to a JDK that provides that API.

## 2. What Does Preview API Mean?

In Java, a *preview feature* is a mechanism allowing developers to try a feature whose design and implementation are complete yet **not yet permanently standardized**. The goal of preview is to gather real-world feedback before the API is finalized or changed.

Crucial point: **preview does not mean an arbitrary experimental API without a contract**. The JDK still provides API documentation and usage rules. However, preview users must accept that subsequent releases may change the API surface, behavior, or even whether the feature persists.

| Concept | Meaning for Gatherers |
| --- | --- |
| `preview` (Java 22/23) | API exists in the JDK but must be enabled explicitly; not yet a permanently stable platform part |
| `second preview` (Java 23) | An additional feedback round before standardization; **still** requires enabling preview |
| `final` (Java 24) | API becomes an official component of Java SE; no separate preview flag needed |
| `incubator` | Another experimental Java mechanism; **not** the status of Stream Gatherers in JDK 22/23 |
| `deprecated` | API marked discouraged/recommended against; **not synonymous** with preview |
| `LTS` | Support policy for a JDK release, **distinct** from an API's preview/final status |

Specifically, "Java 24 finalized Gatherers" **does not mean** every custom Gatherer operation in an application is automatically correct, optimal, or parallel-safe. It is a statement about **the API's status in the platform**, not a test result for business code.

### 2.1. Why Were There Two Preview Rounds?

Java 22 introduced Stream Gatherers so users could test defining stateful intermediate operations. Java 23 kept the feature in a second preview to collect more feedback and refine it further. Java 24 standardized the mechanism into an official API.

Even when an example uses factories with identical names between Java 22 and Java 24, do not assume **all code using custom Gatherer implementations or old preview class files** can be reused as-is without verification.

## 3. Correct Compile and Run Commands by Version

We will use a small program named `GathererVersionDemo.java`. The program uses `windowFixed(3)` to group numbers into three-element windows.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererVersionDemo {
    public static void main(String[] args) {
        List<List<Integer>> batches = Stream
            .of(1, 2, 3, 4, 5, 6, 7)
            .gather(Gatherers.windowFixed(3))
            .toList();

        System.out.println(batches);
        // [[1, 2, 3], [4, 5, 6], [7]]
    }
}
```

This example uses basic API names that existed across the preview rounds and in JDK 24. However, **it must be compiled separately with the target version's JDK** and the flags applied per case.

### 3.1. Java 22 — Preview per JEP 461

Use `javac` and `java` from **JDK 22**:

```bash
javac --enable-preview --release 22 GathererVersionDemo.java
java --enable-preview GathererVersionDemo
```

Here:

- `--release 22` specifies Java 22's target API and bytecode.
- `--enable-preview` permits using preview features belonging to **release 22**.
- At runtime, `java --enable-preview` must be supplied with the matching JDK 22 environment.

Do not try replacing `--release 22` with `--release 21` to "still use Java 22 APIs while running on Java 21": Java 21 does not have those APIs.

### 3.2. Java 23 — Second Preview per JEP 473

Use JDK 23:

```bash
javac --enable-preview --release 23 GathererVersionDemo.java
java --enable-preview GathererVersionDemo
```

**Second preview is not enabled automatically.** The `Gatherer` and `Gatherers` classes in JDK 23 are still marked preview. Do not drop `--enable-preview` merely because the API has already undergone one review round.

When upgrading a project from Java 22 to 23, **recompile** with JDK 23 and inspect all uses of preview APIs, especially if the project implements custom `Gatherer<T,A,R>`, `Integrator`, `combiner`, or `finisher`. Do not rely on identical API names to guarantee binary compatibility.

### 3.3. Java 24 — Official API per JEP 485

Use JDK 24:

```bash
javac --release 24 GathererVersionDemo.java
java GathererVersionDemo
```

Or, once certain that `javac` and `java` belong to JDK 24:

```bash
javac GathererVersionDemo.java
java GathererVersionDemo
```

**No** `--enable-preview` is needed for Stream Gatherers. Attempting to compile with JDK 21 or setting `--release 21` remains incompatible, because `Gatherer` does not exist in Java 21.

### 3.4. Comparison Command Table

| Environment | `javac` Command | `java` Command | Uses Standard Gatherer? |
| --- | --- | --- | --- |
| JDK 21 | `javac --release 21 ...` | `java ...` | No |
| JDK 22 | `javac --enable-preview --release 22 ...` | `java --enable-preview ...` | Yes, preview |
| JDK 23 | `javac --enable-preview --release 23 ...` | `java --enable-preview ...` | Yes, preview 2 |
| JDK 24 | `javac --release 24 ...` | `java ...` | Yes, official |

The ellipsis `...` in the table represents the application's specific source file or class name, not a literal shell argument.

## 4. Why `--enable-preview` Does Not Solve Every Version Error

`--enable-preview` only enables **preview features provided by the JDK currently in use**; it is not a switch that downloads features from a future Java release.

Cases to distinguish:

- **JDK 21 + `--enable-preview`:** still no standard `Gatherers`. Java 21 does not ship JEP 461.
- **JDK 22 + preview disabled:** using Gatherers is rejected by the compiler because the API is in preview status.
- **JDK 23 + `--release 22` and preview enabled:** not a way to run Java 22 previews on JDK 23's compiler. Preview is tied to the compiler's **current release**.
- **JDK 24 + `--release 21`:** cannot use Java 24's `Stream.gather` to produce an artifact claiming Java 21 compatibility.
- **JDK 24 + `--release 24`:** uses the official Gatherer API with no preview flag required.

### 4.1. Preview Bytecode Must Be Treated as a Deployment Constraint

Java versions mark and verify class files that use preview features. When upgrading from an older preview JDK, **do not move old class files/build artifacts directly to the new JDK expecting them to run**. The safe strategy is:

1. Choose the new target JDK.
2. Clean old compilation outputs.
3. Recompile all Gatherer-using code under that JDK.
4. Run semantic tests, including empty, short-circuit, and parallel cases.
5. Verify the actual runtime of the deployment environment.

Source files using preview APIs on JDK 22/23 may need adjustments when moving to JDK 24, especially custom Gatherers; **do not assume binary compatibility merely because the program compiled at an earlier milestone**.

### 4.2. JDK, Java Runtime, and `--release` Are Not the Same Thing

Run:

```bash
java -version
javac -version
```

to verify whether both tools belong to the intended JDK version. `--release` controls the compilation target, yet **does not install a JDK/runtime on the server**.

An application compiled to Java 24 bytecode also cannot run on a Java 17 or 21 runtime simply by tweaking flags. This holds independently of Gatherer logic.

## 5. What Does the Official Java 24 API Include?

Three main entry points live in `java.base`, package `java.util.stream`:

| Component | Role |
| --- | --- |
| `Stream.gather(Gatherer)` | Applies a Gatherer intermediate operation to a pipeline |
| `Gatherer<T, A, R>` | Contract of an intermediate operation that can hold state, emit outputs, and handle end-of-stream |
| `Gatherers` | Built-in Gatherers for windows, running scans, folds, and concurrent mapping |

Key `Gatherers` factories in Java 24:

| Factory | Output | Problem |
| --- | --- | --- |
| `windowFixed(k)` | `Stream<List<T>>` of non-overlapping batches | Groups every `k` elements, including a shorter final batch |
| `windowSliding(k)` | `Stream<List<T>>` of sliding windows | Tracks the most recent `k` elements |
| `scan(initial, scanner)` | Emits **accumulated result after each element** | Running totals, prefix scans |
| `fold(initial, folder)` | Emits **one result** after reducing the entire source | Reduces to a single value with stateful/ordered rules |
| `mapConcurrent(maxConcurrency, mapper)` | Maps with bounded concurrency while preserving result order | Tasks executable concurrently using virtual threads |

Java 24 also provides methods supporting custom Gatherers, such as `Gatherer.of(...)`, `Gatherer.ofSequential(...)`, `Gatherer.Integrator`, `Gatherer.Downstream`, and `Gatherer.andThen(...)`.

### 5.1. `Gatherer` Does Not Replace `Collector`

Example:

```text
Stream<Order>
   |
   +-- filter(...)     : select elements
   |
   +-- map(...)        : transform each element
   |
   +-- gather(...)     : custom INTERMEDIATE operation
   |                     may accept multiple elements,
   |                     maintain state and emit multiple results
   |
   +-- collect(...)    : TERMINAL operation aggregating final result
   v
Report
```

`Collector` (available since Java 8) is the aggregation mechanism at the **end of a pipeline**. `Gatherer` (preview 22/23, final 24) expands the catalog of **intermediate operations**. A Gatherer can produce `Stream<List<Order>>` before a collector groups or aggregates metrics.

Do not replace `reduce` or `collect` with a custom Gatherer when built-in tools express the result directly and more simply.

## 6. Complete Java 24 Example: Two Window Types and Running Sum

The following program compiles with **JDK 24** without enabling preview:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GatherersFinalDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(10, 20, 30, 40, 50);

        List<List<Integer>> fixed = numbers.stream()
            .gather(Gatherers.windowFixed(3))
            .toList();

        List<List<Integer>> sliding = numbers.stream()
            .gather(Gatherers.windowSliding(3))
            .toList();

        List<Long> running = numbers.stream()
            .map(Integer::longValue)
            .gather(Gatherers.scan(
                () -> 0L,
                Long::sum
            ))
            .toList();

        String combined = Stream.of("A", "B", "C")
            .gather(Gatherers.fold(
                () -> "",
                String::concat
            ))
            .findFirst()
            .orElseThrow();

        System.out.println("fixed = " + fixed);
        System.out.println("sliding = " + sliding);
        System.out.println("running = " + running);
        System.out.println("fold = " + combined);
    }
}
```

Output:

```text
fixed = [[10, 20, 30], [40, 50]]
sliding = [[10, 20, 30], [20, 30, 40], [30, 40, 50]]
running = [10, 30, 60, 100, 150]
fold = ABC
```

Run:

```bash
javac --release 24 GatherersFinalDemo.java
java GatherersFinalDemo
```

The example shows:

- `windowFixed(3)` produces a final batch with **fewer than three elements**.
- `windowSliding(3)` produces overlapping windows in encounter order.
- `scan` emits the accumulated value **after every element**; it does not drop old elements from the total like a sliding window.
- `fold` produces a single result from the whole source, unlike `scan`, which emits a stream of intermediate results.
- Each `numbers.stream()` call creates a new Stream because a Stream that has passed through a terminal operation **cannot be reused**.

Data rules and JDK versions are separate concerns: when moving from preview to final, still test output values, empty-source handling, and ordering.

## 7. Important Edge Cases of Windows

The Java 24 specification defines concrete rules that must be covered in tests. For `k = 3`:

| Input Data | `windowFixed(3)` | `windowSliding(3)` |
| --- | --- | --- |
| `[]` | `[]` | `[]` |
| `[1]` | `[[1]]` | `[[1]]` |
| `[1,2]` | `[[1,2]]` | `[[1,2]]` |
| `[1,2,3]` | `[[1,2,3]]` | `[[1,2,3]]` |
| `[1,2,3,4]` | `[[1,2,3],[4]]` | `[[1,2,3],[2,3,4]]` |
| `[1,2,3,4,5]` | `[[1,2,3],[4,5]]` | `[[1,2,3],[2,3,4],[3,4,5]]` |

Both factories require a positive size; passing `k < 1` throws `IllegalArgumentException`.

On an ordered source:

- `windowFixed(k)` emits a shorter final window if total elements are not divisible by `k`.
- `windowSliding(k)` with `0 < N < k` emits **one** shorter window containing the entire source.
- When `N >= k`, `windowSliding(k)` emits `N-k+1` full windows.
- Each window list from standard factories is **unmodifiable**; do not call `add` or `remove`.

This is API semantics, not an artifact of the preview phase. If the application requires processing only full-size windows, add a business filter:

```java
List<List<Integer>> fullWindows = Stream.of(1, 2)
    .gather(Gatherers.windowSliding(3))
    .filter(window -> window.size() == 3)
    .toList();

System.out.println(fullWindows); // []
```

## 8. Custom Gatherers on Java 24: Reading the Contract

A `Gatherer<T, A, R>` has three type parameters:

- **`T`**: input element type.
- **`A`**: internal accumulation state type (*state*).
- **`R`**: type of elements emitted downstream.

Common roles:

| Component | Purpose |
| --- | --- |
| `initializer` | Creates fresh state for a traversal pass |
| `integrator` | Receives an element, updates state, and may emit results |
| `combiner` | Merges branch states if the Gatherer is designed to parallelize |
| `finisher` | Emits additional results at end-of-stream if needed |

In cases with a single **order-dependent** state, usually start with `Gatherer.ofSequential(...)`. If you want the Gatherer to split in parallel, **a valid combiner** is required, not just adding `.parallel()` outside.

### 8.1. Custom Gatherer Example Emitting Sum After Each Element

```java
import java.util.List;
import java.util.stream.Gatherer;

public class CustomGatherer24Demo {

    static Gatherer<Integer, int[], Integer> runningSum() {
        return Gatherer.<Integer, int[], Integer>ofSequential(
            () -> new int[] {0},
            (state, value, downstream) -> {
                state[0] = Math.addExact(state[0], value);
                return downstream.push(state[0]);
            }
        );
    }

    public static void main(String[] args) {
        List<Integer> output = List.of(3, 5, 7)
            .stream()
            .gather(runningSum())
            .toList();

        System.out.println(output); // [3, 8, 15]
    }
}
```

This example deliberately uses `int[]` as internal mutable state to highlight the roles of `initializer` and `integrator`. State **must never be stored in a shared static variable** across runs.

In business code that only needs an ordinary running sum, `Gatherers.scan(() -> 0, Integer::sum)` is shorter and easier to maintain. Custom Gatherers help when the transformation or stop/emit rule cannot be expressed directly by built-in factories.

### 8.2. Why Must Custom Code Be Re-Checked When Upgrading JDKs?

Preview releases supplied the contract and tools for building Gatherers, yet API details could be refined across preview rounds. Thus when moving to Java 24:

1. Re-read signatures in Java 24 `Gatherer`/`Gatherer.Integrator`.
2. Check whether initializer/combiner/finisher match the finalized contract.
3. Ensure the integrator respects the boolean return signal from `downstream.push(...)`.
4. Compare sequential vs. parallel results and short-circuiting cases.
5. Use `ofSequential` when an operation lacks a valid combiner.

The fact that `Gatherers.windowFixed(3)` looks nearly identical across JDKs **does not guarantee** every custom Gatherer written during preview behaves correctly without retesting.

## 9. Can You Keep Java 17/21 and Use Official Gatherers?

**You cannot directly call standard Stream Gatherers on Java 17/21.** Neither `java.util.stream.Gatherer`, `Gatherers`, nor `Stream.gather` belongs to the API of those releases. Enabling `--enable-preview` will not make them appear.

If a system must support Java 17/21, design options include:

| Approach | Pros | Trade-off |
| --- | --- | --- |
| Continue using `filter/map/reduce/collect` | Compatible with older JDKs, minimal change | Some stateful transformations are awkward to express |
| Use loops, custom `Iterator`, or custom `Spliterator` | Full control over windows/state | Must test edge cases and resources yourself |
| Isolate a module requiring Java 24+ | Allows official Gatherers in newer component | Separate deployment/runtime requirements |
| Upgrade minimum supported JDK to 24+ | Uses official API directly | Affects servers, CI, libraries, and operations |
| Use an external library offering a similar mechanism | May reduce hand-written code | Not identical to standard `java.util.stream.Gatherer`; vendor dependency |

Do not call another library's helper API "the exact Java 24 Gatherer" if that library only mimics the concept. Similar names do not create automatic type or behavioral compatibility.

### 9.1. Example Replacing `windowFixed` with a Loop on Java 17

For data already in a `List`, non-overlapping batches can be built with Java 17-compatible code:

```java
import java.util.ArrayList;
import java.util.List;

public class FixedWindows17 {
    static <T> List<List<T>> fixedWindows(List<T> data, int width) {
        if (width < 1) {
            throw new IllegalArgumentException("width must be >= 1");
        }

        List<List<T>> result = new ArrayList<>();

        for (int start = 0; start < data.size();) {
            int end = start + Math.min(width, data.size() - start);

            result.add(List.copyOf(data.subList(start, end)));
            start = end;
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println(fixedWindows(
            List.of(1, 2, 3, 4, 5), 3
        )); // [[1, 2, 3], [4, 5]]
    }
}
```

This is a **result-equivalent solution for a finite `List` source**, not a Java 17 version of `Gatherer`. It materializes the entire list of windows and does not become a lazy intermediate operation.

**Arithmetic safety note:** the example computes the upper bound via `start + Math.min(width, data.size() - start)` to avoid overflowing `int` if `width` is huge; it also advances via `start = end`. In real applications, check input size, element types, and `null` handling; `List.copyOf` rejects `null` elements.

### 9.2. Example Replacing `windowSliding` with a Loop on Java 17

```java
import java.util.ArrayList;
import java.util.List;

public class SlidingWindows17 {
    static <T> List<List<T>> slidingWindows(List<T> data, int width) {
        if (width < 1) {
            throw new IllegalArgumentException("width must be >= 1");
        }

        if (data.isEmpty()) {
            return List.of();
        }

        if (data.size() < width) {
            return List.of(List.copyOf(data));
        }

        List<List<T>> result = new ArrayList<>();

        for (int start = 0; start <= data.size() - width; start++) {
            result.add(List.copyOf(
                data.subList(start, start + width)
            ));
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        System.out.println(slidingWindows(
            List.of(1, 2, 3, 4, 5), 3
        )); // [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
    }
}
```

This replacement mimics the **output semantics** of `windowSliding` for a finite, ordered, `null`-free source. It **does not** carry all guarantees of laziness, short-circuiting, parallelism, or concrete list behavior of the standard Gatherer. That must be documented clearly in compatibility notes.

## 10. Strategy for Upgrading a Project from Preview to Java 24

When a project already tried Stream Gatherers on Java 22 or 23, do not view upgrading as merely "removing one flag". There are three layers of work:

### 10.1. Updating Toolchain and Runtime

- Choose JDK 24 or a newer JDK that includes official Gatherers and aligns with the project's support policy.
- Verify the actual versions of `javac`, `java`, IDE, and CI.
- Update `--release` or Java toolchain settings to match the target version.
- Remove `--enable-preview` **if no other preview features remain in use**.
- Ensure servers, containers, and deployment images run a runtime meeting the target version.

If CI still runs JDK 23 while developer machines run JDK 24, local execution does not prove CI builds will succeed.

### 10.2. Recompiling and Handling APIs

- Clean-compile instead of reusing class files or JARs built by an older preview compiler.
- Check imports of `java.util.stream.Gatherer` and `java.util.stream.Gatherers`.
- Verify `Gatherer.of`/`ofSequential` overloads and lambda types.
- Remove workarounds only needed during preview if official APIs now supersede them.
- Compare target APIs against preview versions if the application implements stateful custom Gatherers.

Do not change code merely to make syntax compile while ignoring business requirements to preserve prior behavior.

### 10.3. Semantic and Performance Testing

Key tests:

1. Empty streams and single-element sources.
2. Source size less than, equal to, and greater than `windowSize`.
3. `windowFixed` with an incomplete final batch.
4. `windowSliding` with overlapping windows and encounter order.
5. Integrators with early stopping when downstream stops accepting.
6. Side effects, shared state, and parallel execution.
7. `Files.lines` or I/O cursors with explicit closing responsibilities.
8. Arithmetic overflow and floating-point rounding error.
9. Memory allocation costs for large windows and throughput in real runs.

**Final API status does not replace software testing.**

## 11. Maven and Gradle Configuration: Must Reflect the Target JDK

No builds were run while authoring this lesson; the snippets below merely illustrate how to configure a Java project when moving to official Gatherers.

### 11.1. Maven — Java 24 Target

In `pom.xml`:

```xml
<properties>
    <maven.compiler.release>24</maven.compiler.release>
</properties>
```

You must use a Maven runtime/compiler or toolchain with a **JDK supporting Java 24**. The `maven.compiler.release` property does not install JDK 24 automatically. Maven Compiler Plugin versions and toolchain settings must also suit the environment.

If preview flags were previously configured for JDK 23, audit **compiler, test runner, IDE JVM, and deployment environment** settings alike. Do not leave `--enable-preview` enabled mechanically once the project has fully moved to official APIs.

### 11.2. Gradle — Java 24 Toolchain

Example using Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 24
}
```

The Gradle version in use must support the chosen Java toolchain. Ensure an appropriate JDK is available locally or configured for download via the toolchain mechanism.

**Note:** `toolchain` selects the compiler/runtime for build tasks, whereas `options.release` restricts target APIs/bytecode. Setting `release = 21` on JDK 24 tooling **forbids** referencing Java 24 Stream Gatherers APIs in code compiled with release 21.

### 11.3. If You Still Must Build for Java 22/23 Preview

The respective build systems must pass `--enable-preview` to both the compiler **and** the JVM running tests/applications on that exact preview JDK version. Do not copy preview configuration from Java 22 to a Java 24 environment without auditing all flags.

## 12. When One Codebase Must Support Multiple JDKs

Suppose a library has customers on Java 17 and customers on Java 24. There are two different requirements:

- **Ability to run on Java 17:** code loaded on a Java 17 runtime must not require absent APIs.
- **Ability to leverage Gatherers on Java 24:** a newer implementation can be provided in an appropriate module/variant.

A relatively clear architecture:

```text
Common business API
      |
      +-- Java 17 Implementation
      |      loops, Iterator, or built-in Stream/Collector
      |
      +-- Java 24+ Implementation
             official Stream.gather / Gatherers
```

Use shared tests to compare outputs of both implementations. You can package them into separate artifacts and select the dependency by supported runtime, or consider advanced packaging structures if the team truly needs them.

**Do not simply compile a JAR on JDK 24 and claim "Java 17 support"** if required classes link to `Stream.gather` or `Gatherers`. Targeting bytecode down to an older version while using newer APIs is likewise not solved by `--release`.

If using reflection to probe for newer APIs, carefully design class loading/linking timing, public API types, and fallbacks; reflection does not magically make a Java 24-dependent program compatible with Java 17. For learning projects or typical applications, two explicit implementations are usually easier to maintain.

## 13. `mapConcurrent` in Gatherers Differs from `parallelStream`

`Gatherers.mapConcurrent(maxConcurrency, mapper)` is a built-in Gatherer using **virtual threads** to run the mapper concurrently up to a specified limit. It attempts to preserve **result ordering** of the Stream.

```java
import java.util.List;
import java.util.stream.Gatherers;

public class ConcurrentGatherer24Demo {
    public static void main(String[] args) {
        List<Integer> lengths = List.of("A", "Java", "Stream")
            .stream()
            .gather(Gatherers.mapConcurrent(
                3,
                String::length
            ))
            .toList();

        System.out.println(lengths); // [1, 4, 6]
    }
}
```

This differs from:

```java
List<Integer> lengths = List.of("A", "Java", "Stream")
    .parallelStream()
    .map(String::length)
    .toList();
```

Both approaches may produce **the same result** in this example, yet their scheduling model, concurrency bounds, and performance impact are **not identical**.

- `mapConcurrent` takes a `maxConcurrency` bound and uses virtual threads per API contract.
- `parallelStream` uses Stream's parallel execution mechanism, without an equivalent `maxConcurrency` parameter directly on `parallel()`.
- Preserving output order **does not mean** subtasks execute sequentially.
- Every mapper must still obey safety contracts for state, exceptions, I/O, and resources.
- Do not assume higher concurrency is always faster, especially for CPU-bound workloads or when target systems have connection limits.

A program migrating from preview to Java 24 should re-measure `mapConcurrent` on representative workloads rather than looking only at small example results.

## 14. Gatherers, State, and Parallel Processing

Finalizing the API does not remove foundational Stream rules:

- **Non-interference:** do not mutate the source while the pipeline traverses it, unless the source supports it by contract.
- **Stateless behavior:** for `map`, `filter`, and most element-processing lambdas, avoid depending on external mutable state.
- **Confinement:** internal state of a sequential Gatherer must not become a global variable mutated by multiple pipelines simultaneously.
- **Combiner correctness:** if designing a parallelizable Gatherer, the combiner must merge state accurately with respect to ordering and business semantics.
- **Short-circuiting:** a terminal operation like `findFirst` or `limit` may not request all input elements.

Example to avoid:

```java
// Do not do this: using an external mutable List to collect all results.
List<Integer> shared = new java.util.ArrayList<>();

Stream.of(1, 2, 3, 4)
    .parallel()
    .gather(Gatherers.scan(() -> 0, Integer::sum))
    .forEach(shared::add);
```

`ArrayList` is not safe for concurrent writes from multiple threads; moreover, `forEach` on a parallel Stream does not guarantee encounter order for side effects. The proper way is:

```java
List<Integer> running = Stream.of(1, 2, 3, 4)
    .gather(Gatherers.scan(() -> 0, Integer::sum))
    .toList();

System.out.println(running); // [1, 3, 6, 10]
```

Some parts may execute sequentially due to Gatherer characteristics. That **must not be used** as an excuse for side effects on state outside the pipeline: changing the implementation or Gatherer type can re-expose the bug.

## 15. I/O Resources and Laziness Do Not Change Just Because the API Is Final

`Stream.gather(...)` is an intermediate operation. If the source is `Files.lines(path)`, file resources must still be closed in the proper ownership scope, even when running on Java 24.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FileGatherer24Demo {
    public static List<List<String>> readBatches(Path path)
            throws IOException {
        try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .filter(line -> !line.isBlank())
                .gather(Gatherers.windowFixed(100))
                .toList();
        }
    }
}
```

**Notes:**

- `try-with-resources` closes `Files.lines` upon exiting the block, even if `map`/`filter`/terminal operations throw exceptions.
- `gather` and `toList()` do not replace calling `close()` on I/O sources.
- `toList()` stores all resulting windows in memory, which can cause high memory usage for huge files.
- Placing `filter` before `gather` changes how elements are grouped into windows. If the goal is batching **100 raw lines** instead of 100 non-blank lines, change the order of operations.

In applications freshly upgraded from preview, also check custom I/O sources, close handlers, and early-termination behavior. Standardizing the API does not automatically free resources.

## 16. Minimum Compatibility Verification Suite Before Release

A test matrix avoids confusing "compiles on one machine" with "product supports the target JDK properly".

| Item | JDK 22 preview | JDK 23 preview | JDK 24 final |
| --- | --- | --- | --- |
| Correct compiler JDK | Verify | Verify | Verify |
| Enable preview at compile time | **Yes** | **Yes** | **No** for Gatherer |
| Enable preview at runtime | **Yes** | **Yes** | **No** for Gatherer |
| Test `windowFixed`/`windowSliding` | Yes | Yes | Yes |
| Test custom `Gatherer` | Per JDK 22 | Per JDK 23 | Per JDK 24 |
| Test empty/short inputs | Yes | Yes | Yes |
| Test ordering and parallel behavior | Yes | Yes | Yes |
| Test I/O source cleanup | Yes | Yes | Yes |
| Verify fresh build artifacts, no old preview classes | Yes | Yes | Yes |

### 16.1. Illustrative Test Suite on JDK 24

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GathererContractCheck24 {
    public static void main(String[] args) {
        var fixed = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowFixed(3))
            .toList();

        var sliding = Stream.of(1, 2, 3, 4, 5)
            .gather(Gatherers.windowSliding(3))
            .toList();

        var shortInput = Stream.of(1, 2)
            .gather(Gatherers.windowSliding(3))
            .toList();

        var empty = Stream.<Integer>empty()
            .gather(Gatherers.windowFixed(3))
            .toList();

        if (!fixed.equals(List.of(
                List.of(1, 2, 3),
                List.of(4, 5)))) {
            throw new AssertionError("fixed windows mismatch");
        }

        if (!sliding.equals(List.of(
                List.of(1, 2, 3),
                List.of(2, 3, 4),
                List.of(3, 4, 5)))) {
            throw new AssertionError("sliding windows mismatch");
        }

        if (!shortInput.equals(List.of(List.of(1, 2)))) {
            throw new AssertionError("short input mismatch");
        }

        if (!empty.isEmpty()) {
            throw new AssertionError("empty stream mismatch");
        }

        System.out.println("Gatherer contract checks passed");
    }
}
```

Assertions verify **public semantics** of built-in Gatherers. Do not assert internal class names or how many times an integrator is invoked, since implementations are allowed to optimize the pipeline.

### 16.2. Rules for Cross-Checking Results Between Two Implementations

If maintaining both a Java 17 fallback and a Java 24 Gatherer:

1. Test on the exact same ordered input dataset.
2. Test with the same window size and the same trailing-short-batch rule.
3. Compare **result lists**, not specific Map/List implementation class names.
4. Test `null` values or invalid-input cases per each implementation's contract.
5. Check memory consumption and how much data gets materialized.
6. Only declare equivalence if business conditions genuinely match.

A loop-based fallback over a `List` may yield identical results to a Gatherer on sample data while differing in laziness and handling of infinite sources. **Result equivalence on finite sets does not imply equivalence across all API properties.**

## 17. Common Error Table When Moving Across JDKs

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| `cannot find symbol: Gatherers` on JDK 17/21 | API does not exist yet | Upgrade JDK or use an alternative |
| Compiler says Gatherer is a preview API | Using JDK 22/23 without preview enabled | Enable `--enable-preview` and release matching that JDK |
| Running on JDK 22/23 reports preview disabled | Runtime lacks preview flag or misconfigured build | Run `java --enable-preview` on the matching JDK |
| Trying to compile Java 22 preview with JDK 23 and `--release 22` | Preview is bound to the active JDK release | Compile with JDK 22 itself or raise target to 23 and test |
| Java 24 still carries old preview flags across CI/tests | Uncleaned config or another preview feature in use | Audit each feature and keep flags only when genuinely needed |
| Compiling `--release 21` while using `Stream.gather` | Java 24 API is not in release 21 | Raise target or separate implementations |
| Build passes in IDE but fails in CI | Different JDKs/toolchains | Pin and verify toolchain across all environments |
| Artifacts built under old preview fail after runtime upgrade | No cross-JDK preview artifact compatibility guarantee | Clean build and recompile on target JDK |
| `windowFixed(k)` leaves a short trailing window | Normal API contract | Filter for full-size windows if required |
| `windowSliding(k)` on short source still emits one window | Normal API contract | Choose warm-up vs. full-window policy |
| Trying to call `gather` directly on `IntStream` | `gather` API is on object `Stream<T>` | Convert via `boxed()` or choose a suitable primitive algorithm |
| Custom Gatherer mutates a global variable | Unsafe state sharing | Use initializer to create per-execution state |
| Adding `parallel()` and assuming it is faster | Splitting/merging/state overhead can be large | Benchmark and verify ordering |
| Skipping `close()` on file sources after `gather` | Resource leak | Close using `try-with-resources` |
| Calling the final API and assuming it "validates" data | Confusing API stability with business correctness | Verify filtering rules, state, numeric types, and outputs |

### 17.1. Primitive Stream Case

`Stream.gather` is declared on `Stream<T>` (object stream). Given an `IntStream`, you can convert to `Stream<Integer>` to use a Gatherer:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

List<List<Integer>> windows = IntStream.rangeClosed(1, 5)
    .boxed()
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(windows); // [[1, 2], [3, 4], [5]]
```

`boxed()` can introduce boxing cost; for very large numeric volumes, benchmark and consider a custom primitive solution if Gatherers become a bottleneck.

## 18. Practice Exercises

### Exercise 1: Identifying API Status

Build a table for Java 17, 21, 22, 23, and 24: does `Stream.gather` exist, must preview be enabled, and which JEP serves as the primary specification? Explain why Java 23 is still not considered the final release.

### Exercise 2: Writing Exact CLI Commands

For `GathererVersionDemo.java`, write the compile/run commands on JDK 22, JDK 23, and JDK 24. Explain the different roles of `--enable-preview` and `--release`.

### Exercise 3: Spotting Backward-Compatibility Bugs

A library builds with JDK 24 and calls `Gatherers.windowFixed` yet still claims Java 17 runtime support. Analyze the contradiction and propose two mitigation strategies.

### Exercise 4: Comparing Fallbacks

Write a Java 17 loop producing three-element fixed windows and compare outputs with `windowFixed(3)` in Java 24. Test `N=0`, `N=2`, `N=3`, and `N=5`. Why can the two solutions still differ in laziness?

### Exercise 5: Sliding Window Policy

For data `[10, 20]` and `k=3`, what does `windowSliding` emit? Write a pipeline emitting only full windows. Explain when a "warm-up" metric is acceptable vs. when full samples must be awaited.

### Exercise 6: `scan` and `fold`

Use `Gatherers.scan` to produce the running sum of `[2, 3, 5]`. Use `Gatherers.fold` to produce a single final sum. Distinguish output element counts and emission timing; test an empty Stream too.

### Exercise 7: Custom Gatherers and State

Create a `Gatherer.ofSequential` emitting the sum after each element. Why must state not be placed in a shared static `int[]`? When is a combiner needed for parallel processing?

### Exercise 8: CI Configuration

Suppose developer machines use JDK 24, CI runners use JDK 23, and servers run Java 21. Write an ordered upgrade plan: choosing target, adjusting flags, upgrading runtimes, clean builds, and regression testing.

### Exercise 9: `mapConcurrent` and Ordering

On Java 24, use `Gatherers.mapConcurrent` to map a list of strings to lengths. Compare results with `parallelStream().map(...)`. Explain why identical outputs do not mean identical concurrency models or performance.

### Exercise 10: Does an Official Release Change Business Logic?

Suppose a preview custom Gatherer generates alerts from temperature windows. After upgrading to JDK 24 and removing `--enable-preview`, which tests must still run? Emphasize alert thresholds, empty data, short windows, unordered sources, and I/O exceptions.

## 19. Self-Check Questions

- In which JDK did Gatherers debut in preview, and in which JDK were they standardized?
- Which three stages do JEP 461, 473, and 485 correspond to?
- Why is `--enable-preview` required on JDK 22/23 but not needed for Gatherers on JDK 24?
- Why does enabling preview on JDK 21 not create `java.util.stream.Gatherers`?
- Does `--release 21` allow using Java 24 APIs when the compiler runs on JDK 24?
- Is `Stream.gather` an intermediate or terminal operation?
- Do `Gatherers.windowFixed` and `windowSliding` handle short sources the same way?
- How does `Gatherers.scan` differ from `Gatherers.fold` in output count?
- When should `Gatherer.ofSequential` be preferred over declaring a custom combiner?
- Why must old preview class files be rebuilt and retested when upgrading JDKs?
- Should a global `ArrayList` be used to collect Gatherer outputs in a parallel Stream?
- Why does `mapConcurrent` differ from `parallelStream` even though both can run multiple tasks?
- If an application must support Java 17, what options exist besides upgrading the whole system?
- Why does a finalized API not automatically guarantee code correctness, thread safety, or high performance?

## 20. Official References

1. [JEP 461 — Stream Gatherers (Preview)](https://openjdk.org/jeps/461): first preview in JDK 22.
2. [JEP 473 — Stream Gatherers (Second Preview)](https://openjdk.org/jeps/473): second preview in JDK 23.
3. [JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485): API standardization in JDK 24.
4. [Oracle Java SE 22 — Gatherers API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/stream/Gatherers.html): Javadoc marked preview with factories in JDK 22.
5. [Oracle Java SE 23 — Gatherers API](https://docs.oracle.com/en/java/javase/23/docs/api/java.base/java/util/stream/Gatherers.html): API documentation still marked preview.
6. [Oracle Java SE 24 — Gatherers API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html): official factories.
7. [Oracle Java SE 24 — Gatherer API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): initializer/integrator/combiner/finisher contract.
8. [Oracle Java SE 24 — Stream Gatherers Guide](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html): examples and applying Gatherers.
9. [Oracle Java SE 22 — Preview Features](https://docs.oracle.com/en/java/javase/22/language/preview-language-and-vm-features.html): rules for enabling preview in compiler and runtime.
10. [Oracle JDK 24 Release Notes](https://www.oracle.com/java/technologies/javase/24-relnote-issues.html): details on Stream Gatherers entering the standard library.

**Key takeaway:** **Java 22 = preview (JEP 461), Java 23 = second preview (JEP 473), Java 24 = official API (JEP 485).** On Java 22/23, enable preview at compile time and run on the matching JDK; on Java 24, this flag is not required just to use Gatherers. **An official API does not mean code runs on older JDKs, does not remove state/resource management duties, and does not replace testing.** When upgrading versions, choose a consistent toolchain, clean build, verify the target runtime, and thoroughly test pipeline semantics.