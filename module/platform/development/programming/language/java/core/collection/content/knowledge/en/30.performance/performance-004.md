# Boxing, Object Allocation, Garbage Collection, and Memory Locality

## 1. From Collection Operations to Hardware Costs

Two ways of storing and traversing the same set of numbers can share an O(n) complexity yet differ significantly in execution time, allocation volume, and retained memory. Big O describes how the number of operations scales with input size; it does not fully capture the costs of type conversions, object count, pointer chasing, or waiting for data from memory.

In this lesson, four concepts connect to one another:

- **Boxing**: converting a primitive value, such as `int`, into a wrapper object like `Integer`.
- **Allocation**: reserving memory for objects or arrays that actually materialize at runtime.
- **Garbage collection (GC)**: identifying and reclaiming memory occupied by objects that no longer need to be kept alive according to JVM reachability rules.
- **Memory locality**: the degree to which subsequent memory accesses can take advantage of data that is already nearby or loaded into CPU caches.

The causal chain can look like this:

```text
Choose data representation and collection type
    -> primitive values or object references needed?
    -> boxing, nodes, replacement backing arrays, or temporary objects involved?
    -> allocation volume, live data size, and reference graph change
    -> GC work and memory access paths change
    -> throughput, latency, and memory footprint may change
```

This is an analytical framework for forming hypotheses and taking measurements, not a blanket rule claiming that every collection involving boxing is slow in every scenario.

## 2. Where Do Boxing and Unboxing Occur?

### 2.1. Generic Collections Hold Reference Types

In Java 17/21, generic type arguments must be reference types. `List<Integer>` is valid, whereas `List<int>` is not. As a result, a standard list of integers typically holds references to `Integer` instances, while an `int[]` stores primitive values directly.

The following snippet illustrates the conversions; place it inside a method with appropriate imports:

```java
List<Integer> values = new ArrayList<>();
int input = 1_000_000;
values.add(input);        // int -> Integer: boxing
int output = values.get(0); // Integer -> int: unboxing
```

Conceptually, these conversions correspond to obtaining a wrapper object and reading back the primitive value, commonly emitted as `Integer.valueOf(input)` and `intValue()` in compiled bytecode. That conceptual mapping is not a guarantee of the physical object count after JIT optimizations.

A loop like `for (int value : values)` also unboxes each retrieved element. Arithmetic operations on wrapper variables may unbox operands before computing, and then box the result again if assigned back to a wrapper variable. The conversion rules are specified in [JLS §5.1.7–§5.1.8](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7).

### 2.2. Wrapper Object Caching Is Not CPU Caching

`Integer.valueOf(int)` reuses instances for at least the range `-128` to `127`, and may cache other values outside that range as well. Consequently, boxing does not always allocate a new object. [`Integer.valueOf` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#valueOf(int)).

It is important to distinguish between the two uses of the word "cache":

| Mechanism | What Is Reused | Primary Effect |
| --- | --- | --- |
| `Integer` object cache | Certain wrapper object instances | Can avoid allocating new wrapper objects |
| CPU cache | Blocks of memory loaded close to the CPU by hardware | Can reduce latency when accessing data |

Reusing an `Integer` instance does not guarantee that every access to it will be a CPU cache hit. Conversely, a newly allocated object may still enjoy favorable cache locality during a given execution phase.

Never use `==` between two `Integer` variables to test numeric equality. It compares reference identity and may only coincidentally produce the expected result due to wrapper caching. Use `equals`, `Objects.equals` when `null` is possible, or convert to primitives after handling `null` according to business requirements. Do not rely on a large value to assert that two boxing operations will definitely yield distinct references.

### 2.3. `null` and Semantics Must Be Resolved Before Optimization

A collection of wrapper types may permit `null`, whereas a primitive `int` cannot represent `null`. Unboxing a `null` reference throws a `NullPointerException`.

When migrating from `List<Integer>` to `int[]` or a specialized primitive data structure, you must decide how to represent missing data. Do not arbitrarily replace `null` with `0` if `0` is a valid domain value. Reducing allocations must never alter program correctness.

## 3. Allocations Come from More Than Just Boxing

A collection operation can involve several categories of objects:

| Potential Allocation Source | Example | What to Distinguish |
| --- | --- | --- |
| Wrapper objects | Inserting numeric values into a reference collection | Caching or JIT optimizations may avoid some allocations |
| Structural nodes | Adding elements to a linked list or entries to a hash table | The structural node and the payload object are two distinct objects |
| New backing arrays | Growing an array-backed list | Allocating a new array does not mean deep-copying the elements |
| Intermediate collections | Creating a result list at each processing stage | Multiple lists may reference the same underlying element objects |
| Support objects | Iterators, stream pipeline objects, or capturing lambdas in some cases | Do not assume every call always materializes a physical object |

For example, pre-sizing an `ArrayList` can reduce replacement backing arrays, but it does not eliminate boxing in `add(intValue)`. Similarly, switching from `LinkedList<Integer>` to `ArrayList<Integer>` eliminates node objects, yet the reference array and `Integer` objects remain.

### 3.1. Counting Operations in Source Code Is Not Counting Physical Objects

The JVM can optimize away certain objects that do not escape the scope of a computation, using techniques such as escape analysis and scalar replacement. These capabilities depend on the JVM implementation, execution paths, and JIT compilation decisions; not every temporary object is eliminated. [HotSpot Performance Enhancements documentation](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html).

Therefore, both of the following claims are unfounded:

- "The code performs 10,000 boxing conversions, so it definitely allocates exactly 10,000 objects."
- "The JIT has escape analysis, so all boxing inside loops is free."

Objects stored inside a returned collection or retained for later use have very different escape constraints than objects used solely within a local calculation. You must measure the actual allocation volume of the specific workload under representative compilation conditions.

### 3.2. A Wrapper Accumulator Easily Creates Unnecessary Work

Consider this example:

```java
Long total = 0L;
for (int value : primitiveValues) {
    total += value;
}
```

Semantically, each iteration must unbox the `long` value from `total`, add `value`, and box the result back into a `Long`. Unless `null` representation is required or an API explicitly demands a wrapper during accumulation, using `long total = 0L` clarifies intent and avoids repeated boxing requests at the source level. If the method must return a `Long`, box once at the return boundary rather than using a wrapper type throughout the accumulation loop.

The actual physical object count still requires empirical verification; this example explains an avoidable source of work rather than prescribing a fixed byte count or GC frequency.

## 4. From Allocation to Garbage Collection Work

### 4.1. Allocating a Lot vs. Retaining a Lot Are Two Distinct Problems

Separate three distinct metrics:

1. **Allocation volume per unit of work**: for instance, bytes allocated per request or per full batch run.
2. **Allocation rate**: bytes allocated per second.
3. **Live data set**: the objects that must remain alive at a given point in time.

One service might generate a high volume of short-lived objects while retaining only a small live set. Another service might allocate very little per second while retaining a massive map for hours. Looking solely at heap occupancy at a single snapshot does not adequately characterize either workload.

As a hypothetical arithmetic example: if each request allocates 2,000 bytes and the system processes 10,000 requests per second, the allocation rate is 20,000,000 bytes/second. This is simply the product of the two numbers, not a prediction of GC pause frequency. After an optimization, if the allocation rate per second drops merely because the program processes fewer requests, you cannot conclude that efficiency improved; evaluate bytes per request alongside throughput and latency.

### 4.2. Why Do Short-Lived Objects Still Carry a Cost?

The JVM can allocate small objects very quickly. However, the system still requires memory for them; high allocation volume increases the pressure to reclaim or reuse memory regions. GC work also depends on the number of surviving objects, the references that must be traced, the collector implementation, and heap configuration.

With G1 on JDK 21, most ordinary allocations go into young-generation regions, whereas humongous objects follow dedicated handling. Evacuation may need to copy surviving objects. Understanding this mechanism helps explain why object lifetime matters as well; however, do not generalize G1's internal process to every garbage collector. [G1 Collector documentation](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-g1-garbage-collector1.html).

Do not assume that allocating one extra object immediately triggers a GC cycle, nor that halving the object count always halves pause times. The relationship also depends on heap state, object sizes, lifetimes, and concurrent activity.

### 4.3. Collections Can Unintentionally Extend Object Lifetimes

A temporary list discarded as soon as a request finishes is far less problematic than an unbounded cache that retains every result indefinitely. As long as an object remains strongly reachable from a live collection, the garbage collector cannot unilaterally decide that the data is "stale and disposable."

Common application patterns to inspect include:

- Maps used as caches without a maximum size or eviction policy.
- Session-bound lists that continue accumulating data across many old requests.
- Queues whose long-term ingestion rate exceeds their processing rate.
- Collections held in `static` fields or long-lived components unintentionally.

Managing object lifetimes and bounding data growth usually has a much more direct impact than trying to force the GC to reclaim data that is still strongly referenced. `System.gc()` is merely a hint asking the JVM to make an effort toward reclamation, with no guarantee regarding the amount of memory reclaimed or the exact timing. [`System.gc` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#gc()).

## 5. Memory Locality: Where Must the CPU Go to Fetch a Number?

### 5.1. `int[]`, `ArrayList<Integer>`, and Linked Lists

The diagram below illustrates the levels of indirection; exact physical memory addresses are managed by the JVM:

```text
int[]
  [1000][1001][1002][1003]          values stored directly inside the array

ArrayList<Integer>
  [ref0][ref1][ref2][ref3]          references stored inside the array
     |     |     |     |
     v     v     v     v
  Integer Integer Integer Integer   wrapper objects live outside the array

LinkedList<Integer>
  node0 -> node1 -> node2 -> node3  must follow node links
    |        |        |        |
    v        v        v        v
  Integer  Integer  Integer  Integer
```

Sequentially traversing an `int[]` reads primitive values laid out contiguously inside the array itself. Traversing an array-backed list of wrapper numbers requires reading a reference from the backing array and then dereferencing it to read the primitive field inside the target `Integer` object. A linked list adds a separate node layer and depends on chasing the pointer to each subsequent node.

Contiguous slots in a reference array do not imply that the referenced objects themselves lie contiguously in memory. Objects may have been allocated at different times or relocated across GC cycles. Never infer physical memory adjacency merely from collection element order.

### 5.2. CPU Caches and Contiguous Access

CPUs typically load memory in cache-line blocks. Traversing closely packed data allows multiple elements to be served from a single fetched cache line and helps hardware prefetchers predict upcoming accesses. Chasing multiple references across scattered heap locations can cause the CPU to stall waiting for memory, especially when the working set exceeds CPU cache capacity.

This provides the theoretical basis for hypothesizing that a denser data representation can improve traversal speed. Actual results still depend on dataset size, access pattern, hardware architecture, and the amount of computation performed per element.

An official JMH sample compares a primitive array, a list of boxed integers, and a list with shuffled element references to demonstrate the impact of memory access patterns. Do not treat the specific timing numbers in that sample as universal constants across machines. [JMH: Memory Access](https://raw.githubusercontent.com/openjdk/jmh/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_39_MemoryAccess.java).

### 5.3. Do Not Blame Algorithmic Complexity on CPU Caches

If you traverse a `LinkedList` by calling `get(i)` for every index, each call may have to walk the node chain. The entire loop degrades to O(n²) instead of the O(n) achieved with an iterator. A massive performance gap in such a benchmark stems from the access algorithm long before memory locality enters the picture.

A sound analytical progression checks algorithmic complexity and operation count first, then examines data representation, allocation volume, and memory access paths. Big O and memory locality complement each other; neither replaces the other.

## 6. Java 17+ Program Verifying Semantics

Save as `BoxingDemo.java`. This is a standalone program with no external dependencies:

```java
import java.util.ArrayList;
import java.util.List;

public class BoxingDemo {
    public static void main(String[] args) {
        Integer first = 42;
        Integer second = 42;
        System.out.println("cached identity=" + (first == second));

        Integer largeA = Integer.valueOf(1_000_000);
        Integer largeB = Integer.valueOf(1_000_000);
        System.out.println("same numeric value=" + largeA.equals(largeB));

        int[] primitive = new int[5];
        List<Integer> boxed = new ArrayList<>(primitive.length);
        for (int i = 0; i < primitive.length; i++) {
            primitive[i] = 1_000_000 + i;
            boxed.add(primitive[i]);
        }

        long primitiveSum = 0;
        for (int value : primitive) {
            primitiveSum += value;
        }

        long boxedSum = 0;
        for (int value : boxed) {
            boxedSum += value;
        }

        Long boxedAccumulator = 0L;
        for (int value : primitive) {
            boxedAccumulator += value;
        }

        long streamSum = boxed.stream()
                .mapToLong(Integer::longValue)
                .sum();

        System.out.println("primitive sum=" + primitiveSum);
        System.out.println("boxed sum=" + boxedSum);
        System.out.println("boxed accumulator=" + boxedAccumulator);
        System.out.println("primitive stream sum=" + streamSum);

        boxed.add(null);
        try {
            int missing = boxed.get(boxed.size() - 1);
            System.out.println(missing);
        } catch (NullPointerException ex) {
            System.out.println("unboxing null=NullPointerException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 BoxingDemo.java
java BoxingDemo
```

Exact stdout:

```text
cached identity=true
same numeric value=true
primitive sum=5000010
boxed sum=5000010
boxed accumulator=5000010
primitive stream sum=5000010
unboxing null=NullPointerException
```

How to interpret the output:

- Boxing the constant `42` twice demonstrates instance reuse within the guaranteed small cache range. This does not make `==` a valid numeric equality check for wrapper types in general.
- Larger values are compared using `equals`; the program does not assert that the two references must be distinct.
- The primitive array and the boxed list produce the exact same sum; this proves semantic equivalence of the result, not equal execution speed.
- `Long boxedAccumulator` computes the right sum but semantically requires unboxing and re-boxing on compound addition assignment. Standard output alone does not reveal how many allocations the JIT compiler eliminated.
- `mapToLong` uses a primitive `long` stream for the summation stage, although the source list still holds `Integer` references that must be read.
- Only after computing all sums does the program append `null`. Unboxing that trailing element throws a `NullPointerException`, which is caught to print deterministic output.

This program does not measure execution time, object counts, or GC behavior. Do not wrap it in a `nanoTime()` loop and draw performance conclusions from a few runs.

## 7. Avoiding Unnecessary Boxing in Processing Pipelines

### 7.1. Keep Primitive Values in Computation Loops

Use `int`, `long`, or `double` for local computation variables whenever semantics allow. Box only at boundaries that require objects, such as passing a result into a generic API. For large sums, also choose a primitive type with sufficient range; avoiding boxing does not prevent arithmetic overflow.

If the input already resides in a `List<Integer>`, unboxing during summation is necessary to perform arithmetic. A worthwhile optimization is avoiding the creation of additional intermediate boxed collections just to hold temporary results that will immediately be unboxed again.

### 7.2. Use Primitive Streams When Appropriate

Consider this example inside a method where `List<Integer> values` is already available and contains no `null` elements:

```java
long total = values.stream()
        .mapToLong(Integer::longValue)
        .sum();
```

`Stream<Integer>` is an object reference stream, whereas `IntStream`, `LongStream`, and `DoubleStream` are primitive specializations. Transitioning to a primitive stream for downstream stages can avoid boxing intermediate values at each step. However, a stream pipeline still has its own runtime machinery; do not describe it as "allocating zero objects whatsoever." [`java.util.stream` package documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html).

Calling `.boxed()` converts elements back into a stream of wrapper objects. And if the pipeline ultimately collects into a `List<Integer>`, the requirement to represent final elements as wrapper objects remains. Likewise, `mapToInt` does not retroactively erase `Integer` objects that already exist in the source collection.

### 7.3. Change Data Structures When Usage Requirements Permit

Primitive arrays work well for many numeric workloads where the size is known or explicitly managed. Third-party primitive collection libraries can offer richer operations, provided you evaluate their API contracts, missing-value semantics, and measured performance within your actual project.

Do not replace a fast lookup map with a linear array scan just to reduce object count while ignoring lookup complexity. Nor should you force rich domain models into raw primitive arrays simply because arrays are denser. A data structure must satisfy access patterns, update requirements, and correctness first; optimize measured bottlenecks afterward.

## 8. Designing Measurements to Avoid False Conclusions

### 8.1. Separate Distinct Questions

| Measurement Target | What Goes Inside the Measured Operation | Question Answered |
| --- | --- | --- |
| Building a collection | Allocating the collection, inserting elements, returning the result for consumption | What is the cost of constructing and materializing the representation? |
| Traversing an existing collection | Traversal/computation only; dataset prepared outside the timed region | What is the cost of reading the structure and computing the result? |
| End-to-end request or batch processing | The entire representative processing path | Does the optimization improve the real-world service objective? |

If one benchmark variant builds the collection inside the timed method while another variant reads a pre-built collection, the comparison fails to isolate traversal cost. Conversely, measuring traversal alone does not tell you the total cost of constructing and discarding a collection on every request.

To isolate structural overhead between two reference collections, pass the exact same pre-allocated element objects into both. If each variant boxes its own fresh set of objects, the measurement mixes structural differences with wrapper allocation and heap layout differences. Always document which scenario you are deliberately measuring.

### 8.2. Control Microbenchmark Pitfalls

Use JMH for serious microbenchmarking and proper data setup. Key checklist items:

- Include warmup iterations and multiple measurement iterations; run multiple independent forks to evaluate run-to-run stability.
- Return results or consume them via a `Blackhole` so the compiler cannot eliminate dead computations.
- Never print to stdout inside the measured benchmark method.
- Use representative data distributions: small numbers hit the wrapper cache, whereas large numbers can exhibit very different allocation behavior.
- Test multiple dataset sizes, including working sets larger than CPU cache capacities; never extrapolate linearly from a tiny list.
- Keep JDK version, JVM flags, heap size, garbage collector, and hardware environment consistent, and record the exact configuration used.

JMH provides an explicit sample demonstrating how unused computations get eliminated by dead-code elimination. [JMH: Dead Code](https://raw.githubusercontent.com/openjdk/jmh/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java).

### 8.3. Read Multiple Metrics Rather Than Average Time Alone

In JMH, the GC profiler (`-prof gc`) reports both allocation rate and normalized bytes allocated per operation. Interpret `B/op` according to how "one operation" is defined in your benchmark: if a single `@Benchmark` call processes 10,000 elements, `B/op` reflects bytes per 10,000-element batch unless normalized via `@OperationsPerInvocation`.

Evaluate `gc.alloc.rate.norm` alongside execution time and throughput; never treat a lower MB/s rate by itself as independent proof that each request allocates less memory. GC profiling metrics also require sufficient runtime duration and iteration counts to stabilize. [JMH: Profilers](https://raw.githubusercontent.com/openjdk/jmh/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java).

In production applications, monitor throughput, latency percentiles, allocation volume, and GC activity together under representative load. If you suspect premature or unintended retention, inspect heap dumps and reference chains; if you suspect memory access bottlenecks, use appropriate hardware performance counters or profilers rather than guessing cache miss rates from wall-clock time alone.

## 9. Common Misconceptions and How to Correct Them

| Hasty Conclusion | More Accurate Analysis |
| --- | --- |
| "Boxing always allocates a brand-new object." | Account for wrapper caching, reference sharing, and JIT optimizations; measure actual allocations |
| "GC handles memory automatically, so object count does not matter." | GC work carries cost and depends on live data; measure against throughput and latency targets |
| "Fewer GC cycles definitely means faster execution." | The program might simply be doing less work or retaining memory longer; compare equal units of work |
| "`ArrayList<Integer>` stores numbers contiguously in memory." | Its backing array stores contiguous references; the `Integer` objects themselves live outside the array |
| "Equal O(n) complexity means roughly equal traversal speed." | Memory access paths, boxing, object indirection, and per-element computation costs can differ substantially |
| "Switching to a primitive stream eliminates all existing boxing." | Source wrapper objects still exist; the savings apply to downstream stages converted to primitives |
| "Pooling every small object will reduce overhead." | Object pools can extend lifetimes, retain memory, and add bookkeeping or synchronization overhead; measure net benefit |

## 10. Practice: Analyzing a Numeric Processing Pipeline

Suppose each incoming request receives 100,000 numbers, populates a `List<Integer>`, creates a second transformed result list, computes the sum, and then discards both lists. Work through the analysis in order:

1. Verify the expected output, numeric range, missing-value semantics, and overflow risk.
2. Map out where boxing begins, where intermediate collections materialize, and where unboxing occurs for summation.
3. Measure bytes allocated per request, throughput, and latency of the baseline implementation; note how long the result lives.
4. Test computing the result in a single pass or via a primitive stream to avoid materializing the intermediate list if it is not reused.
5. Change the input representation only if the API contract permits; verify output equivalence and re-measure under identical load.
6. If allocation volume drops significantly but latency does not improve, investigate other bottlenecks such as I/O, CPU-bound math, or data access patterns rather than assuming GC was the sole cause.

Self-check questions:

- Why might a benchmark that only uses numbers from `0` to `100` fail to represent arbitrary numeric workloads?
- Why does summing a `List<Integer>` still require unboxing even though the `Integer` objects already exist?
- If you change an accumulator variable from `Long` to `long`, what is simplified semantically and what still needs empirical measurement?
- When the garbage collector cannot reclaim a map full of stale entries, where should you look for the references keeping it alive?
- Why can shuffling the element references inside a list alter traversal performance even though the element count and addition count remain identical?

A strong answer connects data representation to allocation behavior, object lifetime, and memory access paths, and identifies the specific measurement that validates each hypothesis.
