# Measuring the Cost of Crossing the Java/C Boundary Instead of Only Measuring C Algorithm Time

## Objectives

When Java calls a C library via the Foreign Function & Memory API (FFM), JNI, or a similar mechanism, **the execution time of the algorithm on the C side is only part of the actual cost**. The application must also prepare parameters, convert data, possibly copy between heap and native memory, cross the Java/C boundary, receive results, and manage resources. A very fast C algorithm can still slow down an application if it has to be called millions of times for work that is too small.

This lesson guides you on determining the right measurement scope, designing controlled benchmarks, using Java 22+ and C with JMH, reading results, and deciding when to batch, reuse buffers, or stay on the Java side. The focus is on **the cost as seen from the Java caller when receiving a useful result**, rather than just the time a C function runs in isolation.

## 1. Breaking Down the Cost Across Java/C

An actual call may go through:

1. **Java input:** checking conditions, formatting data, converting objects/strings/buffers into types that native code understands.
2. **Interop setup:** loading the shared library, looking up symbols, creating a `MethodHandle`/JNI binding, allocating an arena/buffer. These steps may happen once or repeat per request.
3. **Marshaling and copy-in:** transferring heap arrays to off-heap, UTF-8 encoding, copying struct fields, pinning/copying in JNI depending on the API path.
4. **Cross-boundary:** FFM downcall or JNI native method, passing arguments according to the ABI and coordinating with the JVM.
5. **C algorithm:** computing, reading/writing native memory, and operations inside the C library.
6. **Return and copy-out:** converting results, copying data back to the heap, decoding, mapping errors into exceptions or return codes.
7. **Cleanup:** freeing buffers, handling memory ownership, closing the arena, or releasing JNI resources.

This can be pictured as:

`T_end_to_end ≈ T_prepare + T_copy_in + T_boundary + T_C + T_copy_out + T_cleanup`

This is a **decomposition model**, not an addition formula where each term can always be measured accurately by subtracting numbers. Caches, JIT, GC, memory bandwidth, and optimizations on both sides interact with each other. If objects in production reuse buffers, the cost of creating the buffer does not belong to each call; if created per request, the end-to-end benchmark must include that cost.

**Key point:** a C executable measuring inside a C function only answers "how long does the C algorithm take to run?". It does not answer "how long does it take for Java to call C and process one request?".

### Why a Fast C Function Is Not Necessarily Beneficial

Suppose a call has a fixed overhead `F`, and processing each element costs `W`:

- Calling C `N` times, each call doing one element: `N × (F + W)`.
- Calling C once to process `N` elements: `F + N × W + T_prepare_batch`.

Batching calls can reduce paying `F` many times, but can increase copying, allocation, and latency. Therefore, it is necessary to measure different batch sizes and actual paths, not conclude solely from the formula.

## 2. Building a Controlled Measurement Matrix

| Benchmark | Time Included | Purpose |
| --- | --- | --- |
| Java-only, small addition | Operation inside the JVM | Reference baseline for a very small operation |
| Small C called from Java | FFM/JNI call + one C operation | Observe the call path for a very small operation |
| Java array sum | Java loop over `int[]` | Java-only approach |
| C sum, pre-prepared buffer | Downcall + C loop over off-heap | When data already resides in native memory |
| C sum **with copy** | Copy Java heap → off-heap + downcall + C | When Java must prepare payload for C |
| End-to-end single request | Parse/validate + marshal + C + receive result + cleanup | Decision metric at the application layer |

Do not call the "C already has a pointer" scenario "end-to-end" if real requests always have to transfer `int[]` to native memory. Conversely, if the entire pipeline already uses native memory, intentionally copying again in the benchmark also causes distortion.

FFM and JNI are **two different connection mechanisms**. An FFM benchmark does not directly represent JNI overhead; if comparing JNI/FFM, you need to implement the same C API and workload, keeping data sizes, results, and environment identical.

## 3. Practical Example: Java 22+ Calling C with FFM and Measuring with JMH

The example includes C code, a JMH class, and a Maven configuration. Java 22 is the first version where the FFM API became a standard API (JEP 454). Use JMH 1.37 for warmup, JVM forking, and preventing computation results from being discarded.

### 3.1. Project Structure

~~~text
java-c-benchmark/
├── pom.xml
├── native/
│   └── tiny.c
└── src/
    └── main/
        └── java/
            └── example/
                └── BoundaryBench.java
~~~

### 3.2. Native Library: `native/tiny.c`

~~~c
#include <stdint.h>

#if defined(_WIN32)
    #define EXPORT __declspec(dllexport)
#else
    #define EXPORT __attribute__((visibility("default")))
#endif

EXPORT int32_t add_one(int32_t x) {
    return x + 1;
}

EXPORT int64_t sum_i32(const int32_t *data, int32_t count) {
    int64_t result = 0;
    for (int32_t i = 0; i < count; i++) {
        result += data[i];
    }
    return result;
}
~~~

The `add_one` function is intentionally very small to observe the native call when computational work is low. The `sum_i32` function increases the amount of work according to `count`. Explicit-width types help map `int32_t` ↔ `JAVA_INT` and `int64_t` ↔ `JAVA_LONG`; `int32_t*` ↔ `ADDRESS`. Do not automatically map C `long` to Java `long` across all ABIs: on 64-bit Windows, C `long` is usually only 32 bits.

Compile the library with a command appropriate for the operating system (in the project root directory):

~~~bash
# Linux:
cc -O3 -fPIC -shared -o native/libtiny.so native/tiny.c

# macOS:
cc -O3 -fPIC -dynamiclib -o native/libtiny.dylib native/tiny.c

# Windows with MinGW-w64:
gcc -O3 -shared -o native/tiny.dll native/tiny.c
~~~

Only run the command for the operating system in use. The C compiler and JVM must have the same architecture/ABI; record the compiler version and flags. C receives a valid pointer and length; if the native application reads beyond the allocated memory region, Java `MemorySegment` bounds checking cannot protect against arbitrary C accesses.

### 3.3. JMH Build: `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>java-c-benchmark</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>22</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.openjdk.jmh</groupId>
            <artifactId>jmh-core</artifactId>
            <version>1.37</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.openjdk.jmh</groupId>
                            <artifactId>jmh-generator-annprocess</artifactId>
                            <version>1.37</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.5.3</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals><goal>shade</goal></goals>
                        <configuration>
                            <finalName>benchmarks</finalName>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>org.openjdk.jmh.Main</mainClass>
                                </transformer>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

JMH needs the annotation processor to generate the benchmark harness. The build creates the executable jar `target/benchmarks.jar`, and the forked JVM will receive the native access flag via the annotation in the class in the next step. If using a JDK older than 22 or a C library with the wrong ABI, the example will not run properly.

### 3.4. Benchmark Code: `src/main/java/example/BoundaryBench.java`

~~~java
package example;

import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(value = 2, jvmArgsAppend = "--enable-native-access=ALL-UNNAMED")
public class BoundaryBench {
    @Param({"1", "64", "1024", "16384"})
    public int size;

    public int input = 41;

    private Arena arena;
    private MemorySegment offHeap;
    private int[] heap;
    private long expectedSum;
    private MethodHandle addOne;
    private MethodHandle sumI32;

    @Setup(Level.Trial)
    public void setUp() throws Throwable {
        arena = Arena.ofShared();
        heap = new int[size];
        offHeap = arena.allocate(ValueLayout.JAVA_INT, size);

        for (int i = 0; i < size; i++) {
            heap[i] = i & 255;
            offHeap.setAtIndex(ValueLayout.JAVA_INT, i, heap[i]);
            expectedSum += heap[i];
        }

        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);
        String library = os.contains("win") ? "tiny.dll"
                : os.contains("mac") ? "libtiny.dylib"
                : "libtiny.so";
        Path libraryPath = Path.of("native", library).toAbsolutePath();

        SymbolLookup symbols =
                SymbolLookup.libraryLookup(libraryPath, arena);
        Linker linker = Linker.nativeLinker();

        addOne = linker.downcallHandle(
                symbols.find("add_one").orElseThrow(),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        ValueLayout.JAVA_INT));

        sumI32 = linker.downcallHandle(
                symbols.find("sum_i32").orElseThrow(),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_LONG,
                        ValueLayout.ADDRESS,
                        ValueLayout.JAVA_INT));

        if ((int) addOne.invokeExact(41) != 42
                || (long) sumI32.invokeExact(offHeap, size) != expectedSum) {
            throw new IllegalStateException("Java/C results do not match");
        }
    }

    @TearDown(Level.Trial)
    public void tearDown() {
        arena.close();
    }

    @Benchmark
    public int javaSmall() {
        return input + 1;
    }

    @Benchmark
    public int cSmall() throws Throwable {
        return (int) addOne.invokeExact(input);
    }

    @Benchmark
    public long javaSumHeap() {
        long result = 0;
        for (int value : heap) {
            result += value;
        }
        return result;
    }

    @Benchmark
    public long cSumPreloaded() throws Throwable {
        return (long) sumI32.invokeExact(offHeap, size);
    }

    @Benchmark
    public long cSumWithCopy() throws Throwable {
        for (int i = 0; i < size; i++) {
            offHeap.setAtIndex(ValueLayout.JAVA_INT, i, heap[i]);
        }
        return (long) sumI32.invokeExact(offHeap, size);
    }
}
~~~

**Design explanation:**

- `@State(Scope.Thread)` creates separate state for each benchmark thread. `@Param` creates multiple workload sizes, not just a single measurement point.
- `@Setup(Level.Trial)` creates the arena, allocates the buffer, copies initial data, loads the native library, and creates the `MethodHandle` once. These setup operations **are not included in the benchmark time of each method**. This assumes the application reuses handles/buffers; if in reality setup happens per request, you need to add a benchmark that includes that setup inside the measured region.
- The two `invokeExact` calls match the C descriptors. Pass `MemorySegment` for a pointer in FFM; the native function returns `long`. A wrong signature/ABI can crash the JVM or corrupt memory.
- `javaSumHeap` uses an array on the Java heap, `cSumPreloaded` uses a pre-prepared native buffer, and `cSumWithCopy` copies each element into native memory **inside the measured region**.
- Benchmark methods return real results so JMH can consume them. Setup verifies that native and Java agree on the output before starting measurements. `@TearDown` closes the arena when the trial ends.
- On JDK 22+, restricted native APIs may require `--enable-native-access=ALL-UNNAMED`. `@Fork` passes the flag to the child JVM created by JMH.

This is an example for input-copy and scalar return. If the real API returns arrays, strings, structs, or allocates memory on the C side, you need to add measurement paths for copy-out, decoding, and releasing with proper ownership. You cannot use `cSumPreloaded` to represent those paths.

### 3.5. Running and Saving Results

After building the library in step 3.2, use Maven/JDK 22+ inside the `java-c-benchmark` directory:

~~~bash
mvn -q -DskipTests package
java -jar target/benchmarks.jar "example.BoundaryBench" -prof gc -rf json -rff results.json
~~~

JMH results typically include `Benchmark`, `(size)`, `Mode`, `Cnt`, `Score`, `Error`, `Units`. In this example, `Mode=avgt` and `Units=ns/op` is the average time **for one invocation of the benchmark method**, not the time of "one C operation" if the method also copies data. `Score` depends on the CPU, JVM, compiler, and environment; therefore **do not provide a fixed table of nanosecond numbers** before running on the target machine.

If the library fails to load, check the name `tiny.dll`/`libtiny.so`/`libtiny.dylib`, the `native/` path relative to the working directory when JMH forks, symbol exports, and the architecture of the JVM and C compiler. If creating downcalls is not permitted, check that the child JVM received the native-access flag.

## 4. Analyzing Each Group of Results

### 4.1. Small Functions: `javaSmall` and `cSmall`

When the computation is just adding 1, the Java path can be aggressively inlined by the JIT, while the C path still has to go through a native call. The results may show that calling C for a too-small operation is inefficient. However, **do not directly subtract the two `Score` values and claim that it is a universal FFM overhead constant**: the two paths differ in JIT, data flow, and how they are measured.

If the goal is solely to evaluate the overhead level of the native call path, try adding a family of no-op C functions or functions returning a primitive with the same argument types and no copying; verify that the compiler/JIT does not eliminate the work and repeat under multiple workloads.

### 4.2. Pre-Existing Native Memory: `cSumPreloaded`

This approach is suitable when the application already receives data off-heap, from a native buffer region, or from another pipeline operating on the same memory region. The measurement includes the downcall and C processing on the native buffer, but **does not include creating data or copying from `int[]`**.

Placing it next to `javaSumHeap` only shows the performance of **two pipelines with different data locations**. Do not use that difference to make a general conclusion like "C is faster than Java" or "interop costs X".

### 4.3. With Data Transfer: `cSumWithCopy`

The measurement includes copying `int` values into off-heap using `setAtIndex` and then calling C. This is the more relevant measurement when source data resides on the Java heap. Comparing it with `cSumPreloaded` helps observe the impact of copying, but the measured difference is not a perfect standalone quantification of memcpy because cache, CPU, and JIT also change.

For large payloads, memory bandwidth and caching can dominate most of the time. Also measure the cost of returning large results to Java, encoding/decoding strings, or constructing structs if real requests perform those steps.

### 4.4. The Actual Request Path Determines the Choice

In addition to microbenchmarks, measure a workload that includes all preparation, data transfer, native calling, receiving results, freeing, and related Java business logic. If the service has many concurrent requests, you must also measure concurrency, p50/p95/p99 latency, and throughput. Being faster in single-threaded `ns/op` is not necessarily better under load when the native library has locks, contention, native memory pressure, or queueing.

JMH `-prof gc` measures some JVM allocation/GC metrics; it does not automatically count all native `malloc`, mmap, RSS, or resources held by C. Use an appropriate profiler or OS/native memory metrics when the workload has significant native allocations.

## 5. Variables to Control in Java/C Benchmarks

| Category | Things to Test or Keep Stable | If Ignored |
| --- | --- | --- |
| Number of calls | Per-element calls and batching 1/64/1024/... | Fixed cost per boundary crossing is not visible |
| Payload | Scalar, array, UTF-8 string, struct, large buffer | Marshaling, encoding, and copying are not visible |
| Data location | Heap, pre-allocated off-heap, native-owned buffer | Incomparable comparisons |
| Setup | Load library/lookup symbol once or per request | Missing/overcounting overhead |
| Size | Small fitting in cache, large exceeding cache, random access | Ignoring cache and bandwidth |
| Call direction | Java → C and C → Java callbacks/upcalls | Ignoring reverse-direction cost |
| Concurrency | 1 thread, multiple threads, native locks | Contention is not visible |
| Error path | Success, `errno`, exception mapping | Ignoring failure path cost |
| Cleanup | Buffer pooling, arena close, JNI release | Native allocation/lifecycle is not visible |
| Tooling | JDK, GC, JMH, C compiler, `-O3` optimization, ABI | Results are not reproducible |

With JNI, it is necessary to distinguish `GetIntArrayElements`, `GetPrimitiveArrayCritical`, direct `ByteBuffer`, JNI string conversion, and release/copy-back. Do not assume every call is zero-copy; some APIs may copy or pin depending on the JVM and situation. JNI critical regions have strict restrictions on operations performed while holding the pointer. With FFM, you must also declare the correct `MemoryLayout`, alignment, `Arena` lifetime scope, and ownership; passing a `MemorySegment` does not mean the entire request is copy-free.

## 6. Common Mistakes

**Measuring a single call with `System.nanoTime()`:** clock overhead, JIT warmup, class loading, OS scheduling, and clock resolution can overwhelm a small function. Use JMH warmup, multiple iterations/forks, and monitor error margins. `nanoTime()` is still useful for long tasks or clearly scoped instrumentation.

**Not consuming the result:** the Java/C compiler may eliminate unobservable computations or optimize loops into constants. Return results to JMH, use `Blackhole` when appropriate, and verify correctness outside the measured region; do not scatter `volatile` everywhere because it changes the workload.

**Measuring only C-only:** a C executable does not include JNI/FFM, heap/off-heap copying, decoding, and setup. Keep C-only measurements if you want to find bottlenecks on the C side, but place them alongside a Java caller benchmark following the real path.

**Comparing two different algorithms:** one side uses SIMD or batching, the other calls one element per invocation, or they differ in error conditions/precision. When comparing overhead, keep the work equivalent. When comparing production options, clearly state the differences and ensure correct output.

**Mixing cold start with steady-state:** loading libraries, creating handles, and JIT warmup can be significant for short-lived programs but do not represent post-warmup latency. Measure both modes separately if both matter, and label each result clearly.

**Not controlling the environment:** measuring on a heavily loaded machine, CPU frequency scaling, different JDK/compiler versions. Record JDK vendor/version, CPU/OS, 32/64-bit, JVM flags, C compiler flags, JMH version, and input data. Run multiple forks and check variance.

**Assuming batching always wins:** batching reduces call count but can increase copying, memory, tail latency, lock hold time, and request wait time; conclude using throughput *and* p95/p99 under the required load.

## 7. Finding the Break-Even Point and Choosing an Architecture

For the same workload size `n`, record at least:

1. `T_java(n)`: executed in Java with equivalent data/state.
2. `T_native_prepared(n)`: native processing when data is already in suitable memory.
3. `T_native_full(n)`: Java prepares/copies, calls native, processes output, and cleans up as in a real request.

Find the threshold where `T_native_full(n)` is lower than `T_java(n)` **consistently across multiple forks, larger than measurement noise, and still meets latency requirements**. If `T_native_prepared(n)` is low but `T_native_full(n)` is high, data transfer may be the bottleneck. In that case, consider reusing native buffers, reducing representation conversions, batching multiple elements per call, or keeping an entire processing stage on the same side of the boundary. If the workload is already native from the start, use that context instead of forcing the entire request to copy from the heap.

In particular, a high-performance application should **not** use native for small scalar operations even if the C loop runs faster, because the total cost of interop and maintaining native code does not offset the benefit.

## 8. Verification Checklist

- [ ] Is the measurement scope clearly described: C-only, FFM/JNI prepared, with copy, or end-to-end?
- [ ] Does at least one benchmark actually start from the Java caller and go through the production interop API?
- [ ] Are input/output equivalent, results consumed, and correctness verified?
- [ ] Are copy-in, copy-out, encoding, allocation, and cleanup included when real requests require them?
- [ ] Are warmup/JIT, forks, compiler flags, CPU/JDK version, and error margins recorded?
- [ ] Have multiple payload sizes, native call counts, and batch sizes been measured?
- [ ] If there are callbacks, strings, structs, error handling, or native malloc, have they been measured?
- [ ] Have latency, throughput, and memory/GC been examined under appropriate load?
- [ ] Is the optimization decision based on the real Java → C → Java data path?

## References

- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM finalized in Java 22.
- [Java 24 — Foreign Function and Memory API](https://docs.oracle.com/en/java/javase/24/core/foreign-function-and-memory-api.html): downcalls, library lookup, memory segments, and native access.
- [OpenJDK JMH](https://github.com/openjdk/jmh): microbenchmarking principles, harness, forking, and warmup.
- [JMH samples](https://github.com/openjdk/jmh/tree/master/jmh-samples): examples of using JMH and JIT optimization pitfalls.

**Remember:** Cost must be measured from **the point Java begins interacting** until **a usable Java result is obtained**. A C-only benchmark is a component measurement; end-to-end Java/C measurement is what reflects the decision to use native in the system.