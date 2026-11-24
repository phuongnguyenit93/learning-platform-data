# collectList, collectMap, reduce, and scan in Project Reactor

## 1. What Are These Four Operators Used For?

A **Flux<T>** in Spring WebFlux/Project Reactor can emit many elements over time. When processing orders, database records, or events, an application typically wants one of four outcome shapes:

1. **Keep all elements** in a List to return in a response or process as a batch.
2. **Build a lookup table** Map keyed by a key selected from each element.
3. **Compute a single final aggregated value**, such as a total amount or maximum value.
4. **Emit the running aggregate after each step**, such as running revenue or current progress.

The four corresponding operators:

| Operator | Typical return type | How results are emitted |
| --- | --- | --- |
| **collectList()** | Mono<List<T>> | Emits a List containing the elements when the source completes successfully |
| **collectMap(...)** | Mono<Map<K,V>> | Emits a Map when the source completes successfully |
| **reduce(...)** | Mono<T> or Mono<A> | Emits a single final accumulated result when the source completes |
| **scan(...)** | Flux<T> or Flux<A> | Emits intermediate accumulated states as elements arrive |

**Key distinguishing point:** collectList, collectMap, and reduce require **onComplete** to produce a final result; scan can emit results **before onComplete**. These operators only change how data is represented/coordinated; they do not make an infinite source finite and do not guarantee inputs fit in memory.

### Quick Visual Example

~~~text
Source:             2 ─── 3 ─── 5 ─── onComplete

collectList:                      [2,3,5] ─── onComplete
reduce(sum):                      10 ──────── onComplete
scan(sum):           2 ─── 5 ─── 10 ──────── onComplete
scan(0, sum):        0 ─── 2 ─── 5 ─── 10 ─ onComplete
~~~

**collectMap** also waits for the source to complete, except its result consists of key → value pairs rather than a list or a total sum.

## 2. collectList: Collecting Every Element into a List

### Syntax, Data Flow, and Types

~~~java
Flux<Integer> source = Flux.just(4, 2, 8, 2);
Mono<List<Integer>> result = source.collectList();
~~~

The snippet above is illustrative code used in a program that already imports Reactor. When subscribing to result, values from source are collected into a List; when the Flux completes successfully, the Mono emits:

~~~text
[4, 2, 8, 2]
~~~

**collectList** preserves duplicates and the **actual onNext order**. If the source emits 4,2,8,2, the List has those exact four elements in that order. However, if **flatMap** was used before collectList for async tasks, result order may differ from input order; collectList does not re-sort them.

Edge cases:

- **Empty source:** Flux.empty().collectList() emits an **empty List** (one onNext containing an empty list), then onComplete.
- **Errored source:** upstream onError causes the Mono to emit an error; a partially collected List is **not** emitted as a successful result.
- **Canceled source:** canceling before completion means there is no final List for that subscription.
- **Non-terminating source:** there is no final List to emit unless the source is terminated/bounded by another condition.

### When Should It Be Used?

Use it for a **finite set of controlled size**: the 20 newest products, a page of search results, a selection list, or data passed to an algorithm expecting a List.

WebFlux controller example in a project that already has ProductDto and productService:

~~~java
@GetMapping("/products")
public Mono<List<ProductDto>> listProducts() {
    return productService.findRecentProducts()
            .map(ProductDto::from)
            .take(100)
            .collectList();
}
~~~

**take(100)** caps the pipeline at 100 collected elements, though if stable pagination is required, you must still design filtering/sorting and pagination queries at the data source. Do not rely solely on take as a substitute for efficient queries.

### Memory Risk

The List must retain elements until the source completes. For n elements, retained memory typically grows as **O(n)** references plus the size of the data/objects. Even though **Mono<List<T>>** emits only one value, that value can be huge. If a source emits indefinitely, unbounded accumulation can cause heap/GC pressure or OutOfMemoryError.

For large datasets, consider pagination, streaming processing, **buffer(size)**, **window(size)**, or computing statistics directly with reduce. When only the latest 1,000 elements are needed, source limits and sampling policies must match business requirements.

## 3. collectMap: Turning a Flux into a Lookup Table

### Common Overloads

~~~java
record Product(String sku, String name) {}

Flux<Product> products = Flux.just(
        new Product("P01", "Pen"),
        new Product("P02", "Notebook")
);

// Key is SKU, value is the full Product.
Mono<Map<String, Product>> bySku =
        products.collectMap(Product::sku);

// Key is SKU, value is just the name.
Mono<Map<String, String>> namesBySku =
        products.collectMap(Product::sku, Product::name);
~~~

This is illustrative code. The **keyExtractor** function determines keys; the overload accepting **valueExtractor** determines the values. The result is emitted only after products completes. For an empty source, the result is an empty Map, not Mono.empty().

### Duplicate Keys: Later Elements Overwrite Earlier Elements

~~~text
Product("P01", "Blue pen")
Product("P02", "Notebook")
Product("P01", "Red pen")
onComplete
~~~

**collectMap(Product::sku, Product::name)** produces:

~~~text
P01 -> "Red pen"
P02 -> "Notebook"
~~~

Because P01 appears a second time, the later value replaces the earlier value. **collectMap does not sum values, keep all duplicate-key records, or automatically pick the newest record by timestamp.** It keeps the later element according to upstream onNext signal order.

If you need all elements for each key, **collectMultimap** is an option:

~~~java
Mono<Map<String, java.util.Collection<Product>>> allBySku =
        products.collectMultimap(Product::sku);
~~~

If you need a sum per key, use **collect(Supplier, BiConsumer)**, group and aggregate, or use **GROUP BY** at the database layer. A complete example of summing per key appears in a later section.

### Map Ordering and mapSupplier

The default Map used by collectMap is a hash-based Map; **do not rely on key iteration order**. Reactor provides an overload:

~~~java
Mono<Map<String, String>> sorted =
        products.collectMap(
                Product::sku,
                Product::name,
                java.util.TreeMap::new
        );
~~~

**TreeMap** produces ascending key order for Strings. **LinkedHashMap** is useful if you want to preserve key insertion order. To get an independent Map per subscription, let the Supplier create a new container; never use a mutable Map implicitly shared across subscriptions.

### Cost

collectMap must retain at least the surviving key/value pairs, so memory cost grows with the number of distinct keys **k** and value sizes. When every element has a distinct key, k can equal the total element count n. For a non-terminating source, the Map can grow indefinitely without ever emitting a final result.

## 4. reduce: A Single Final Accumulation Result

### reduce(aggregator) Without a Seed

~~~java
Mono<Integer> total =
        Flux.just(2, 3, 5).reduce(Integer::sum);
~~~

Inside the operator:

~~~text
Start:     acc = 2
Receive 3: acc = 2 + 3 = 5
Receive 5: acc = 5 + 5 = 10
Source onComplete → Mono emits 10
~~~

In the **reduce(BiFunction<T,T,T>)** overload, the first element becomes the initial state, so:

- **0 elements:** the Mono completes empty (**Mono.empty()**), without emitting 0.
- **1 element:** the Mono emits that element itself; the aggregator does not need to run.
- **N elements:** each element after the first combines with the previous state; the Mono emits the final result only when the source completes.

If the source emits onError, reduce propagates the error; it does not emit a default “partial success” total.

### reduce(seed, accumulator) With a Seed

~~~java
Mono<Integer> total =
        Flux.just(2, 3, 5).reduce(100, Integer::sum);
// Result: 110

Mono<Integer> emptyWithSeed =
        Flux.<Integer>empty().reduce(100, Integer::sum);
// Result: 100
~~~

The seed is the initial accumulation state. With an empty source, the seed still becomes the Mono result:

| Source | reduce(Integer::sum) | reduce(0, Integer::sum) |
| --- | --- | --- |
| 2, 3, 5 | 10 | 10 |
| 5 | 5 | 5 |
| Empty | Mono.empty() | Mono emits 0 |

Therefore, if business logic expects “total is 0” rather than “no data”, choose seed 0 or an explicit default rule. If “no records” must be distinguished from “total equals 0”, preserve the Mono.empty() case or use a result type with status.

### State Type Can Differ from Element Type

~~~java
record Sale(String sku, long cents) {}

Mono<Long> totalCents = Flux.just(
        new Sale("A", 2000),
        new Sale("B", 3500)
).reduce(0L, (sum, sale) -> sum + sale.cents());
// Result 5500L
~~~

**Sale** is the input, and **Long** is the result. This is useful for counts, total amounts, multi-field summary states, and business transformations.

### Accumulator Correctness

Prefer accumulation functions that are clear, well-behaved, and free of side effects:

~~~java
Flux.just(2, 3, 5).reduce(0, Integer::sum);
~~~

Do not update mutable variables placed **outside** the Publisher if multiple subscriptions can run concurrently. If the seed is a mutable List/Map, passing **an existing seed object** into reduce(seed, ...) can cause unintended state sharing across subscriptions. When a fresh seed is needed per subscription, use **reduceWith(Supplier<A>, accumulator)**. For building mutable containers, **collect(Supplier, BiConsumer)** usually expresses intent more clearly.

**reduce does not execute in parallel automatically**. A non-associative or order-dependent function can yield different results if upstream changes emission order. For monetary calculations needing exact precision, typically use **BigDecimal** or small integer units rather than float/double.

## 5. scan: Consecutive Accumulated States

### scan(aggregator) Without a Seed

~~~java
Flux<Integer> running =
        Flux.just(2, 3, 5).scan(Integer::sum);
// Emits sequentially: 2, 5, 10
~~~

Same addition as reduce, except scan emits **each accumulated state**:

~~~text
onNext(2)  → emits 2
onNext(3)  → emits 5
onNext(5)  → emits 10
onComplete → terminates
~~~

**scan(BiFunction<T,T,T>)** uses the first element as the first result; an empty source emits nothing. For a source of n elements completing normally, seedless scan emits n states.

### scan(seed, accumulator): Emits the Initial Seed Too

~~~java
Flux<Integer> running =
        Flux.just(2, 3, 5).scan(100, Integer::sum);
// Emits: 100, 102, 105, 110
~~~

**scan(seed, ...)** emits the seed **immediately as the first state** once the subscription has demand, then emits a new result for each source element. For n elements, the output has **n + 1 states**. For an empty source, scan(seed,...) still emits **the seed** and completes.

If you only want states **after processing at least one data item**, you can use:

~~~java
Flux<Integer> postEventTotals =
        Flux.just(2, 3, 5)
            .scan(100, Integer::sum)
            .skip(1);
// Emits: 102, 105, 110
~~~

Decide explicitly whether the UI/API wants the initial value shown; forgetting this easily causes an off-by-one element bug.

### scanWith: Creating a Seed Per Subscription

~~~java
Flux<Long> running =
        Flux.just(2L, 3L, 5L)
            .scanWith(() -> 100L, Long::sum);
// Emits: 100, 102, 105, 110
~~~

**scanWith(Supplier, accumulator)** initializes the seed per subscription. If the seed is a mutable object, create an independent object per subscription. Yet even with an independent seed, **emitting the same mutable object repeatedly and then mutating it** can cause a Subscriber holding an old reference to see new contents; use immutable snapshots or copy properly when needed.

### When Should scan Be Used?

Suitable for running totals, ingestion progress, processed item counts, stream state, and continuous statistics. Unlike reduce, scan can emit states before the source finishes.

However, scan **does not persist state durably**. To recover after a crash, you need a DB/broker/checkpoint. If the accumulated state is a growing List/Map, scan still risks consuming ever more memory even though its results emit continuously.

## 6. Exact Comparison When the Source Is Empty, Errors, or Never Ends

| Source state | collectList | collectMap | reduce without seed | reduce with seed | scan without seed | scan with seed |
| --- | --- | --- | --- | --- | --- | --- |
| **Empty + onComplete** | Empty List | Empty Map | Mono.empty() | Emits seed | Empty Flux | Emits seed |
| **One element + complete** | Single-element List | Single-key Map | Emits that element | Emits seed+element state | Emits that element | Emits seed and post-element state |
| **N elements + complete** | One N-element List | One Map by key | One final result | One final result | N intermediate results | N+1 results including seed |
| **onError** | No final List emitted; propagates onError | No final Map emitted; propagates onError | No final sum emitted; propagates onError | No final sum emitted; propagates onError | May have emitted some states then onError | May have emitted seed/states then onError |
| **Does not complete** | No final List yet | No final Map yet | No final sum yet | No final sum yet | Can keep emitting each total | Can keep emitting each total |

Error example:

~~~java
Flux<Integer> source = Flux.concat(
        Flux.just(2, 3),
        Flux.error(new IllegalStateException("broken"))
);

Mono<List<Integer>> list = source.collectList();  // onError
Mono<Integer> sum = source.reduce(Integer::sum); // onError
Flux<Integer> progress = source.scan(Integer::sum);
// progress may emit 2, 5, then onError.
~~~

This is an illustrative snippet; do not treat intermediate states before onError as committed transactions. If business logic needs durable outcomes, design persistence/transactions separately.

## 7. Runnable Java 17+ Program: Complete Example

This example uses finite sales data with two repeating product categories to highlight the difference between **taking the last value per key** and **summing all values**. The program uses Reactor Core; **you do not need Spring Boot** to learn these operators.

Layout:

~~~text
reactor-aggregate-demo/
├── pom.xml
└── src/main/java/AggregationDemo.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-aggregate-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>AggregationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **src/main/java/AggregationDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import reactor.core.publisher.Flux;

public class AggregationDemo {
    record Sale(String category, int amount) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("books", 10),
                new Sale("pens", 20),
                new Sale("books", 15),
                new Sale("pens", 7)
        );

        Flux<Sale> source = Flux.fromIterable(sales);

        List<Integer> amounts = source
                .map(Sale::amount)
                .collectList()
                .block();
        System.out.println("collectList = " + amounts);

        Map<String, Integer> lastByCategory = source
                .collectMap(Sale::category, Sale::amount, TreeMap::new)
                .block();
        System.out.println("collectMap = " + lastByCategory);

        Integer sum = source.map(Sale::amount)
                .reduce(Integer::sum)
                .block();
        System.out.println("reduce = " + sum);

        Integer sumWithSeed = source.map(Sale::amount)
                .reduce(100, Integer::sum)
                .block();
        System.out.println("reduce(seed) = " + sumWithSeed);

        List<Integer> running = source.map(Sale::amount)
                .scan(Integer::sum)
                .collectList()
                .block();
        System.out.println("scan = " + running);

        List<Integer> runningWithSeed = source.map(Sale::amount)
                .scan(100, Integer::sum)
                .collectList()
                .block();
        System.out.println("scan(seed) = " + runningWithSeed);

        System.out.println("empty collectList = "
                + Flux.<Integer>empty().collectList().block());
        System.out.println("empty collectMap = "
                + Flux.<Sale>empty()
                    .collectMap(Sale::category, Sale::amount, TreeMap::new)
                    .block());
        System.out.println("empty reduce has value = "
                + Flux.<Integer>empty().reduce(Integer::sum)
                    .blockOptional().isPresent());
        System.out.println("empty reduce(seed) = "
                + Flux.<Integer>empty().reduce(100, Integer::sum).block());
        System.out.println("empty scan = "
                + Flux.<Integer>empty().scan(Integer::sum)
                    .collectList().block());
        System.out.println("empty scan(seed) = "
                + Flux.<Integer>empty().scan(100, Integer::sum)
                    .collectList().block());
    }
}
~~~

With **JDK 17+** and Maven, run in the project directory:

~~~bash
mvn -q compile exec:java
~~~

**Lines printed by the program:**

~~~text
collectList = [10, 20, 15, 7]
collectMap = {books=15, pens=7}
reduce = 52
reduce(seed) = 152
scan = [10, 30, 45, 52]
scan(seed) = [100, 110, 130, 145, 152]
empty collectList = []
empty collectMap = {}
empty reduce has value = false
empty reduce(seed) = 100
empty scan = []
empty scan(seed) = [100]
~~~

**Recalculate the results yourself:**

- The amounts list has four elements **10, 20, 15, 7**.
- With collectMap, the later **books** entry with 15 replaces 10, and the later **pens** entry with 7 replaces 20. TreeMap prints keys in alphabetical order.
- Sum 10 + 20 + 15 + 7 = **52**; with seed 100, the final result is **152**.
- Running totals after each event are **10, 30, 45, 52**.
- Seeded scan emits 100 before adding, then 110, 130, 145, 152.
- The empty lines illustrate the differences among **empty containers**, **Mono.empty()**, and **seeds**.

**Note on block():** The console program uses block() at the boundary to synchronously obtain results from a finite Flux and print them. In a Spring WebFlux service/controller, **return Mono/Flux** for the framework to manage; do not block the event loop with block(), blockLast(), join(), or get().

**Note on multiple subscriptions:** Each line in the example re-subscribes to Flux.fromIterable(sales), a cold source re-reading an in-memory List. If the source is a hot source or a network call with side effects, multiple subscriptions can trigger new work or receive a different dataset. When multiple statistics are needed from **a single emission pass**, design single-pass sharing/aggregation instead of calling block multiple times like the demo.

## 8. collectMap Does Not Sum by Key Automatically

Suppose business logic needs to calculate revenue per category:

~~~text
books: 10 and 15 → total must be 25
pens: 20 and 7   → total must be 27
~~~

**collectMap(Sale::category, Sale::amount)** does not give that result—it gives 15 and 7 due to key overwriting. If you want to sum, you can use **collect(Supplier, BiConsumer)**:

~~~java
Mono<Map<String, Integer>> totals = source.collect(
        () -> new TreeMap<String, Integer>(),
        (map, sale) -> map.merge(
                sale.category(),
                sale.amount(),
                Integer::sum
        )
);
~~~

This snippet uses Sale and source from the previous program. A separate Map is created per subscription, and merge adds amounts per key. Output:

~~~text
{books=25, pens=27}
~~~

This is the general **collect** case, not collectMap. When data is very large, grouping in the database or aggregating over windows can save data transferred through the application.

If you want to keep all Sales belonging to each category, use **collectMultimap(Sale::category)** and then process Map<K, Collection<Sale>>; consider memory costs similar to collectList.

## 9. Associativity, Ordering, and Error-Prone Operations

reduce and scan accumulate in **the order signals arrive**. For adding small integers, results are straightforward. Yet not every operation produces the same result when order changes.

~~~text
Source: 10, 3, 2
Subtraction: (10 - 3) - 2 = 5

Source: 3, 10, 2
Subtraction: (3 - 10) - 2 = -9
~~~

Points to remember:

- **flatMap** can emit asynchronous results in completion order, not necessarily input order.
- **collectList** preserves the observed onNext order; it does not restore original order.
- **collectMap** keeps the later value in **onNext order**; it does not understand timestamps on its own.
- **reduce/scan** reflect data order and the accumulator function; for non-commutative operations, changing order changes the result.
- For monetary data, use **BigDecimal** or integer minor units; float/double have rounding errors, and summing in different orders can produce different decimal digits.
- If order must be preserved across asynchronous processing, consider **concatMap** or **flatMapSequential** depending on goals; measure latency, concurrency, and buffering cost.

Do not assume these operators execute in parallel automatically. Using Flux does not inherently spawn separate threads or boost CPU throughput.

## 10. Infinite Data, Backpressure, and Practical Limits

An example many people misuse:

~~~java
Flux<Long> ticks = Flux.interval(java.time.Duration.ofSeconds(1));

// ticks.collectList() produces no final List when ticks runs infinitely.
Flux<Long> counter = ticks.scan(0L, (count, tick) -> count + 1);
// Can emit 0, 1, 2, 3, ... while the subscription remains active.
~~~

The ticks source is a continuous event sequence. **collectList**, **collectMap**, and **reduce** all wait for onComplete; if the source never completes, the final result never arrives. **scan** is better suited for observing intermediate values, yet also does not stop the subscription on its own.

**Backpressure** regulates demand between Publisher and Subscriber; it does not guarantee that accumulating containers have finite size. Therefore:

| Operator | State retained | Main risk |
| --- | --- | --- |
| collectList | List of all elements | Memory grows with record count |
| collectMap | Map of existing keys/values | Memory grows with distinct key count |
| reduce | One accumulator | Can be O(1) for sum/count; can grow unbounded if accumulator is a List/Map |
| scan | One accumulator and continuous emission | State can be large; creating full snapshots every time can cost CPU/memory |
| scan(...).collectList() | All intermediate scan results | Accumulates back into a large List even though scan initially enabled streaming |

How to reduce risk:

1. **Limit the number of elements** to process, ideally right at the data source (limit, pagination, filter criteria).
2. **Aggregate instead of storing every element** when only sum, count, min/max, or final metrics are needed.
3. **Split into finite windows/buffers** and process chunk by chunk when stats are needed per minute, every N elements, or per page.
4. **Set time limits / cancellation** for external sources; define clear rules when onComplete never arrives or on error.
5. **Measure heap, GC, element counts, key counts, latency, and subscription duration** under realistic load.

Bounded finite source example:

~~~java
Mono<List<Long>> firstHundred =
        Flux.range(1, 1000)
            .take(100)
            .map(Integer::longValue)
            .collectList();
~~~

For reactive queries, use take to enforce an element limit through the pipeline, while still checking the query plan/DB layer if performance matters.

## 11. Mutable State and Multiple Subscribers

In Reactor, a Publisher can often be subscribed to multiple times. If the accumulator is a **mutable object** created outside the pipeline, multiple subscriptions can accidentally mutate the same object together.

A design example to avoid:

~~~java
java.util.ArrayList<Integer> shared = new java.util.ArrayList<>();

Mono<java.util.ArrayList<Integer>> unsafe = Flux.just(1, 2, 3)
        .reduce(shared, (list, value) -> {
            list.add(value);
            return list;
        });
~~~

If subscribed multiple times, shared can retain data from previous runs; concurrent subscriptions can even hit race conditions. Never use this pattern for per-request state.

Use **collect** with a Supplier providing a fresh List:

~~~java
Mono<java.util.List<Integer>> isolated =
        Flux.just(1, 2, 3)
            .collect(
                    java.util.ArrayList::new,
                    java.util.List::add
            );
~~~

Or use **reduceWith** if the design requires an accumulator created lazily per subscription:

~~~java
Mono<java.util.ArrayList<Integer>> isolatedReduce =
        Flux.just(1, 2, 3)
            .reduceWith(
                    java.util.ArrayList::new,
                    (list, value) -> {
                        list.add(value);
                        return list;
                    }
            );
~~~

These are illustrative snippets. With scan and mutable state, also note that **multiple onNext signals may carry the same mutable reference**; create immutable snapshots if downstream retains past states. When using Spring WebFlux, never place a mutable accumulator in a singleton service field to accumulate across independent requests.

## 12. Using in Spring WebFlux: Returning Mono or Flux?

### API Returning a List

~~~java
@GetMapping("/orders")
public Mono<List<OrderDto>> orders() {
    return repository.findRecentOrders()
            .map(OrderDto::from)
            .take(50)
            .collectList();
}
~~~

Appropriate when the client expects a finite JSON array. **OrderDto** and **repository** are assumed to exist; this illustrative code is not a standalone application.

### API Returning a Final Total

~~~java
@GetMapping("/orders/total")
public Mono<Long> totalCents() {
    return repository.findRecentOrders()
            .map(order -> order.amountCents())
            .reduce(0L, Long::sum);
}
~~~

If the source is empty, it returns 0 thanks to the seed. If business logic must distinguish “no records” from “total equals 0”, change the result type or the empty rule.

### API Emitting a Running Total via SSE

~~~java
@GetMapping(
        value = "/orders/running-total",
        produces = org.springframework.http.MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<Long> runningTotal() {
    return repository.findRecentOrders()
            .map(order -> order.amountCents())
            .scan(0L, Long::sum);
}
~~~

scan can emit 0 before the first record appears. With a repository querying only a finite dataset, the stream completes once data runs out; **scan does not automatically push real-time updates** when DB data changes. For real-time updates, connect to an appropriate change/event source.

### API Streaming Record by Record

~~~java
@GetMapping("/orders/stream")
public Flux<OrderDto> stream() {
    return repository.findRecentOrders().map(OrderDto::from);
}
~~~

If the goal is streaming record by record, keep Flux instead of collecting into a List. How the HTTP client receives data depends on media type, codecs, runtime, and consumption; SSE requires an appropriate media type.

**In WebFlux controllers, return Mono/Flux; do not call block() to convert back to synchronous types.**

## 13. Testing with StepVerifier and Edge-Case Inputs

When a project includes **reactor-test**, you can verify signals precisely:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class AggregationChecks {
    static void verify() {
        StepVerifier.create(
                Flux.just(2, 3, 5).reduce(Integer::sum)
        )
        .expectNext(10)
        .verifyComplete();

        StepVerifier.create(
                Flux.just(2, 3, 5).scan(0, Integer::sum)
        )
        .expectNext(0, 2, 5, 10)
        .verifyComplete();

        StepVerifier.create(
                Flux.<Integer>empty().reduce(Integer::sum)
        )
        .verifyComplete();
    }
}
~~~

This is an **illustrative snippet to place in a test project with reactor-test installed**, not a standalone program. Tests should cover:

- collectList preserving onNext order and duplicate elements.
- collectMap keeping the **last value per key**; if all must be kept, verify collectMultimap.
- Seedless reduce on empty having **no onNext**, and seeded reduce emitting the seed value.
- Seedless scan emitting n states, and seeded scan emitting n+1 states.
- Upstream onError: collect/reduce emit no final result; scan may emit states prior to the error.
- Non-terminating sources, cancellation, and memory/resource bounds.
- Asynchronous sources changing emission order: whether the “last value” contract and accumulation operation still hold.
- Multiple subscriptions: whether mutable state is unintentionally shared.

When testing time/asynchronous flows, use appropriate Reactor testing utilities; avoid relying on Thread.sleep to guess unguaranteed ordering.

## 14. Common Mistakes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Assuming **collectMap** sums values per key | Later value overwrites earlier value | Use collect with merge, collectMultimap, or aggregate at the data source |
| Using **reduce** to update UI after every element | Only one final result arrives after onComplete | Use **scan** |
| Forgetting **scan(seed)** emits the seed first | Extra state and easy n vs. n+1 bug | Define UI contract explicitly, consider skip(1) |
| Thinking **seedless reduce** on empty returns 0 | Mono completes empty | Use reduce(0, ...) or handle empty explicitly |
| Collecting an entire infinite Flux into a List/Map | Never produces a final result, risk of memory growth | Bound the source, paginate, or buffer/window |
| Relying on HashMap ordering | Unstable output compared to expectations | Use TreeMap/LinkedHashMap with mapSupplier when needed |
| Sharing a mutable seed across subscribers | State leakage and races | Use a Supplier creating fresh state per subscription |
| Using concurrent flatMap then expecting “latest record” by time | Result depends on onNext arrival order | Sort by business field or choose the right operator |
| Calling **block()** in a WebFlux request | Blocks execution threads | Return Mono/Flux and compose non-blocking operators |
| Treating backpressure as a memory limit for all aggregations | Containers can still grow unboundedly | Set data limits and measure memory/GC |

## 15. Operator Selection Checklist

| Need | Suitable choice |
| --- | --- |
| Want all finite elements, including duplicates | **collectList()** |
| Want one value per key, allowing overwrite on duplicate keys | **collectMap(...)** |
| Want to keep every element belonging to the same key | **collectMultimap(...)** |
| Want a final sum/count/max | **reduce(...)** |
| Want a default result when there are no elements | **reduce(seed, ...)** |
| Want a running total/state after each element | **scan(...)** |
| Want the initial state emitted too | **scan(seed, ...)** |
| Seed must be created fresh per subscription | **reduceWith**, **scanWith**, **collect(Supplier, ...)** |
| Want to sum per key | **collect** with merge, groupBy/aggregation, or GROUP BY query |
| Want to process large volumes in finite batches | **buffer/window**, limits, and pagination |
| Want to stream data over time | Keep **Flux**, or **scan** if running state is needed |

## 16. Conclusion

**collectList** and **collectMap** gather a Flux into a **Mono** holding the final container; collectMap **overwrites** on duplicate keys. **reduce** produces **one final state** and differs between its seeded and seedless overloads on empty sources. **scan** produces **a Flux of intermediate states**; seeded scan also emits the seed before subsequent states.

When choosing an operator, ask yourself: **Does the source complete? Is size bounded? Does order matter? How should duplicate keys be handled? What should an empty source return? Does each subscription have isolated state?** In Spring WebFlux applications, return Mono/Flux directly and keep pipelines non-blocking.

**Official documentation:**
- [Project Reactor Flux API – collectList, collectMap, reduce, scan](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Reactor Reference – Backpressure and request](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html)
