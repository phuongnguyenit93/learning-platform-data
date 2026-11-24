# Stateful Singleton Beans and Concurrency Safety Issues

In Spring, **singleton** is the default bean scope. This means a bean definition is typically created by the container as one shared instance within the scope of **a single ApplicationContext**. When multiple HTTP requests, background tasks, or message listeners use that bean simultaneously, they may invoke methods on the exact same object almost concurrently.

Therefore, a dangerous misconception is: **a singleton bean managed by Spring is automatically thread-safe when accessed by multiple threads**. This is false. Spring manages the creation, provisioning, and lifecycle of the bean; Spring does not automatically lock every field, serialize every method call, or protect mutable state inside the object.

This lesson explains why singletons can suffer from race conditions, lost updates, and visibility issues; how to structure stateless services, immutable data, atomic operations, locks, and concurrent collections; as well as considerations when running HTTP, `@Async`, schedulers, or multiple instances.

## 1. What Does Singleton Scope Mean?

A bean with **singleton** scope is created and managed as a single instance per bean definition within a Spring container. When multiple components inject that same bean, they typically receive references to the same object:

~~~text
Spring ApplicationContext
        │
        ▼
   OrderService bean
   (one instance)
        ▲
        │
   ┌────┼─────────────┐
   │    │             │
   ▼    ▼             ▼
Request A          Request B       Scheduled job
Thread A           Thread B        Scheduler thread
   │                  │                │
   └──────────────┬───┴────────────────┘
                  ▼
          same OrderService object
~~~

Singleton **does not mean**:

- Only one thread is allowed to call the bean.
- The bean's methods always execute sequentially.
- Every field is automatically locked.
- The object is safe when multiple threads modify state concurrently.
- Only one bean instance exists across the entire distributed system.

Singleton is a concept about the **number of instances in a container**, whereas thread safety is a property of **how an object handles concurrent access**. These two concepts are independent.

### Spring Singleton Differs from JVM-Wide Singleton Pattern

A Spring singleton is scoped by container and bean definition. If an application creates two independent ApplicationContexts, each context can have its own instance of the corresponding bean. If an application runs three processes or three pods, each process has its own container and singletons.

~~~text
Process A / ApplicationContext A  → OrderService A
Process B / ApplicationContext B  → OrderService B
Process C / ApplicationContext C  → OrderService C
~~~

Therefore, you should not rely on a singleton field in Spring to store state shared across multiple servers. To share state across instances, you need a shared system such as a database, cache, or message broker with an appropriate consistency mechanism.

## 2. Why Can a Singleton Bean Be Accessed Concurrently?

In a web application, an HTTP server typically processes multiple requests using different execution threads. Spring MVC invokes controllers and services for each request, yet the injected singleton beans can be the exact same instances.

Besides HTTP requests, a bean can also be invoked from:

- Asynchronous methods via **@Async** or an executor.
- Periodic jobs via **@Scheduled**.
- Message listeners processing multiple messages.
- Multiple other services calling the same dependency.
- Callbacks or event handlers triggered by different threads.

For example, a controller and a scheduler both using the same service:

~~~java
@Service
public class ReportService {

    public Report generate() {
        // Read data and generate report.
        return new Report();
    }
}
~~~

If **generate()** only uses local variables and dependencies that are safe under concurrent use, the service can be shared. However, if it writes per-run data into shared fields, multiple threads can interfere with one another.

What matters is not just whether the bean is called from a controller or a scheduler, but **which threads can access the same state at the same time**.

## 3. Stateful and Stateless Beans

A **stateless** bean does not hold per-invocation mutable data in shared fields. It may hold immutable dependencies and use local variables inside methods.

~~~java
@Service
public class TaxCalculator {

    private final TaxPolicy taxPolicy;

    public TaxCalculator(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }

    public BigDecimal calculate(BigDecimal amount) {
        BigDecimal rate = taxPolicy.rateFor(amount);
        return amount.multiply(rate);
    }
}
~~~

In this example, **amount** and **rate** are local variables for each invocation. If **TaxPolicy** is also safe to share, the bean can serve multiple requests without storing per-request state in fields.

A **stateful** bean retains mutable state across invocations:

~~~java
@Service
public class ShoppingCartService {

    private final List<String> items = new ArrayList<>();

    public void add(String item) {
        items.add(item);
    }

    public List<String> getItems() {
        return items;
    }
}
~~~

If this bean is a singleton, all users could be operating on the same **items** list. One user's cart can mix with another's; meanwhile, `ArrayList` is not designed for arbitrary concurrent modification by multiple threads.

~~~text
Customer A ── add("Book") ──┐
                            ▼
                     same items list
                            ▲
Customer B ── add("Phone") ─┘
~~~

The problem here involves both **wrong data boundaries** (whose cart is it?) and **concurrency safety** (multiple threads mutating `ArrayList`). Merely replacing `ArrayList` with a thread-safe collection does not fix customers sharing a single cart.

### Where to Place Per-Request State

Data specific to a single invocation should generally be passed via parameters or a separate object:

~~~java
public Order calculateOrder(
        CustomerId customerId,
        List<OrderLine> lines) {
    // Process data for the current invocation.
}
~~~

If data needs to persist across multiple requests, store it in a database/cache keyed by user or session. If an object needs a lifecycle tied to an HTTP request, request scope can be considered where genuinely appropriate; that scope still does not replace proper data modeling and synchronization when multiple requests access the same session.

## 4. Race Conditions: When Results Depend on Execution Order

A **race condition** occurs when a program's outcome depends on the order or timing of threads operating on shared state.

Example of a bean counting requests:

~~~java
@Service
public class VisitCounter {

    private int count = 0;

    public void increment() {
        count++;
    }

    public int currentValue() {
        return count;
    }
}
~~~

The line **count++** looks like a simple operation, but in reality it can be broken down into:

1. Read the current value of `count`.
2. Add 1.
3. Write the result back to `count`.

Suppose **count = 10** and two threads call `increment` simultaneously:

~~~text
Thread A                       Thread B
--------                       --------
Read count = 10
                               Read count = 10
Add 1 → 11
                               Add 1 → 11
Write count = 11
                               Write count = 11

Actual result: 11
Expected result: 12
~~~

One update is lost, known as a **lost update**. Even though both calls ran, the result only increased by one.

### Common Types of Concurrency Bugs

| Issue | Symptom |
|---|---|
| **Race condition** | Outcome depends on the interleaving order of threads |
| **Lost update** | One update overwrites another update |
| **Visibility problem** | One thread fails to observe the latest change made by another thread as expected by the program |
| **Check-then-act race** | Two threads both check a condition and both perform an action meant to happen only once |
| **Compound operation race** | Multiple individual operations must be treated as a single unit but are not protected together |
| **Deadlock** | Threads hold locks and wait on each other's locks, preventing further progress |

Not every concurrency bug throws an exception. Many bugs only corrupt data at certain moments or under sufficient load, making them hard to reproduce during manual testing.

## 5. Visibility and the Java Memory Model

Beyond two threads writing simultaneously, one thread may write data while another thread does not observe the change in the order the developer expects. This is a **visibility** problem.

~~~java
public class WorkerSwitch {

    private boolean running = true;

    public void stop() {
        running = false;
    }

    public void work() {
        while (running) {
            // Keep working.
        }
    }
}
~~~

If one thread runs **work()** and another calls **stop()** without proper synchronization, the running thread is not guaranteed to observe the change as needed. The compiler or runtime may optimize reads; the Java Memory Model defines the visibility and ordering guarantees a program receives.

### volatile for Simple State

You can declare:

~~~java
public class WorkerSwitch {

    private volatile boolean running = true;

    public void stop() {
        running = false;
    }

    public void work() {
        while (running) {
            // Keep working.
        }
    }
}
~~~

**volatile** ensures reads and writes on that variable have visibility and ordering semantics under the Java Memory Model. When one thread writes **false**, another thread reading the volatile variable observes the written value according to happens-before rules.

However, **volatile does not make every operation on the variable atomic**. For example:

~~~java
private volatile int count;

public void increment() {
    count++;
}
~~~

still has a race condition because **count++** is a multi-step read-modify-write operation. `volatile` is suitable for status flags or references replaced under simple rules; it does not replace locks or atomic operations for compound updates.

## 6. Approach 1: Design Stateless Beans and Use Immutable Data

Often the simplest solution is to avoid holding per-request mutable state in singleton fields. Use method parameters and local variables:

~~~java
@Service
public class DiscountService {

    private final DiscountPolicy policy;

    public DiscountService(DiscountPolicy policy) {
        this.policy = policy;
    }

    public BigDecimal apply(
            BigDecimal amount,
            CustomerTier customerTier) {
        BigDecimal rate = policy.rateFor(customerTier);
        return amount.multiply(rate);
    }
}
~~~

If **DiscountPolicy** is immutable or thread-safe, this service can serve multiple threads. Input data belongs to each invocation and is never stored in shared fields.

### Use Immutable Objects

An immutable object does not allow its state to change after creation. For example:

~~~java
public record DiscountPolicy(
        BigDecimal standardRate,
        BigDecimal premiumRate) {

    public BigDecimal rateFor(CustomerTier tier) {
        return tier == CustomerTier.PREMIUM
                ? premiumRate
                : standardRate;
    }
}
~~~

If the inner values are also immutable, the object can be read safely by multiple threads without locking each access.

**Note:** a `record` only makes its component fields `final` and provides record APIs; if a component is a `List`, `Map`, or other mutable object, `record` does not automatically make that inner object immutable. Make defensive copies or use immutable collections/value types when needed.

### What Does final Mean?

A **final** field can only be assigned once when the object is constructed. It prevents reassigning the reference later and supports stable dependency design:

~~~java
private final OrderRepository repository;
~~~

However, if the reference points to a mutable object like **ArrayList**, declaring the field `final` does not make the list elements immutable and does not make list operations thread-safe.

~~~java
private final List<String> names = new ArrayList<>();
~~~

The **names** field cannot point to a different list after the constructor finishes, yet multiple threads can still concurrently add/remove elements inside that same `ArrayList`. **final protects reference reassignment, not the mutable state of the referenced object.**

## 7. Approach 2: Use AtomicInteger and Atomic Classes

For simple operations such as incrementing a counter, **AtomicInteger** provides atomic operations:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class VisitCounter {

    private final AtomicInteger count = new AtomicInteger();

    public int increment() {
        return count.incrementAndGet();
    }

    public int currentValue() {
        return count.get();
    }
}
~~~

**incrementAndGet()** increments and returns the new value atomically, avoiding the lost update from the plain `int` example.

Common atomic classes:

| Class | Purpose |
|---|---|
| **AtomicInteger** | Atomically update an integer |
| **AtomicLong** | Atomically update a `long` |
| **AtomicBoolean** | Boolean state |
| **AtomicReference<T>** | Atomically replace/read a reference |
| **LongAdder** | Adder suited for multi-threaded statistics with high update frequency |

### Atomics Do Not Automatically Protect Multiple Variables Together

Suppose you need to maintain both **available** and **reserved** such that their sum stays constant. Using two separate `AtomicInteger` instances does not make updating both variables together atomic:

~~~java
available.decrementAndGet();
reserved.incrementAndGet();
~~~

Another thread can observe state between the two operations. If an invariant must hold across multiple fields, protect the entire operation with a lock, an appropriate atomic data structure, or redesign the state as a single object updated atomically via `AtomicReference`.

### LongAdder for Statistics

If you only need to count occurrences under high update contention, **LongAdder** can reduce contention compared to a single atomic variable:

~~~java
private final LongAdder requests = new LongAdder();

public void recordRequest() {
    requests.increment();
}

public long requestCount() {
    return requests.sum();
}
~~~

`LongAdder` fits statistics where reading the sum may reflect an approximate snapshot while concurrent updates are occurring. If you need an exact linearized value at a point in time for business decisions, choose a more suitable mechanism.

## 8. Approach 3: synchronized to Protect Compound Operations

When a multi-step operation must execute as a single unit, **synchronized** can be used:

~~~java
@Service
public class VisitCounter {

    private int count;

    public synchronized int increment() {
        count++;
        return count;
    }

    public synchronized int currentValue() {
        return count;
    }
}
~~~

With a `synchronized` instance method, a thread must acquire the monitor lock on **this** before running the method body. Other `synchronized` instance methods using the same monitor will not execute concurrently on the same object.

~~~text
Thread A ── acquire lock ── increment() ── release lock
Thread B ── wait for lock ── acquire lock ── increment() ── release lock
~~~

When multiple threads call methods on the same singleton instance, operations are protected by the same monitor.

### Synchronizing a Code Block

You do not necessarily have to lock the entire method. A dedicated lock object can be used:

~~~java
public class Inventory {

    private final Object lock = new Object();
    private int available;
    private int reserved;

    public void reserve(int quantity) {
        synchronized (lock) {
            if (quantity <= 0 || available < quantity) {
                throw new IllegalArgumentException(
                        "Insufficient stock");
            }

            available -= quantity;
            reserved += quantity;
        }
    }
}
~~~

Both updates reside inside the same critical section, so other calls using the same lock cannot interleave in between. This example only illustrates synchronization within a single JVM; if inventory is shared across multiple application instances, one process's monitor lock does not protect system-wide data.

### Which Lock Should You Choose?

**synchronized** is usually sufficient for a simple critical section. When advanced capabilities are needed—such as timed lock attempts, interruptible acquisition, multiple conditions, or fairness options—**ReentrantLock** can be used:

~~~java
private final ReentrantLock lock = new ReentrantLock();

public void update() {
    lock.lock();
    try {
        // Modify protected state.
    } finally {
        lock.unlock();
    }
}
~~~

Always place **unlock()** in **finally** to avoid holding the lock if an exception occurs. Locks must be used consistently by every code path accessing the protected state; if one path reads/writes without acquiring the lock, invariants can still be broken.

### Do Not Lock Too Broadly

Holding a lock while making an HTTP API call, reading a large file, or waiting on an external service can force other threads to wait a long time, reduce throughput, and create deadlock risks. Critical sections should be short, clear, and enclose only the operations requiring synchronization.

## 9. Approach 4: Use Concurrent Collections

If a data structure must be shared among multiple threads, consider collections in **java.util.concurrent** instead of non-thread-safe collections.

Example counting events by event type:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class EventStatistics {

    private final ConcurrentHashMap<String, LongAdder> counts =
            new ConcurrentHashMap<>();

    public void record(String eventType) {
        counts.computeIfAbsent(
                eventType,
                key -> new LongAdder())
              .increment();
    }

    public long countFor(String eventType) {
        LongAdder counter = counts.get(eventType);
        return counter == null ? 0L : counter.sum();
    }
}
~~~

**ConcurrentHashMap** supports thread-safe map operations under concurrent access. **computeIfAbsent** creates the value for a missing key according to the map's concurrency semantics. **LongAdder** handles counter updates.

Other concurrent collections:

| Collection | When appropriate |
|---|---|
| **ConcurrentHashMap** | Map read and written by multiple threads |
| **CopyOnWriteArrayList** | Very read-heavy list with infrequent modifications |
| **ConcurrentLinkedQueue** | Non-blocking queue with multiple producers/consumers |
| **BlockingQueue** | Producers/consumers that need to wait when queue is empty or full |
| **ConcurrentSkipListMap** | Sorted map with concurrent operations |

### A Thread-Safe Collection Does Not Make All Logic Thread-Safe

The following snippet can still be wrong:

~~~java
if (!map.containsKey(key)) {
    map.put(key, createValue());
}
~~~

Even when **map** is a `ConcurrentHashMap`, the sequence **containsKey** followed by **put** is two separate operations. Two threads can both observe the key as absent and both create values.

To compute and insert a value into the map in one coordinated operation, you can use:

~~~java
map.computeIfAbsent(key, this::createValue);
~~~

Or another atomic API suited to the requirement. However, watch out for side effects inside the mapping function: avoid performing slow external workflows or non-idempotent work inside map operations if their semantics do not support it.

## 10. ConcurrentHashMap Does Not Solve User Data Boundaries

Returning to the shopping cart example:

~~~java
private final Map<String, List<String>> carts =
        new ConcurrentHashMap<>();
~~~

The outer map may be thread-safe, but each **List<String>** value is still a mutable `ArrayList`. Two requests from the same customer can mutate that list simultaneously; the inner collection remains unsafe under concurrent access.

~~~text
ConcurrentHashMap
  ├── customer-A → ArrayList  ← multiple threads can mutate concurrently
  └── customer-B → ArrayList
~~~

You could use a concurrent collection inside or lock per cart, yet business operations such as adding items, changing quantities, and checking out must still be designed as consistent units. A `ConcurrentHashMap` does not automatically keep item totals, prices, and order statuses consistent.

If cart data must survive restarts or be shared across multiple servers, a database/distributed cache may be a better place to store it. In that case, you need transactions, optimistic locking, distributed locks, or atomic updates fitting the data model.

## 11. Do Different Scopes Solve Thread Safety?

Spring has multiple bean scopes:

| Scope | Instance lifecycle | Automatically guarantees thread safety? |
|---|---|---|
| **singleton** | One instance per bean definition in a container | No |
| **prototype** | Container creates a new instance each time it is requested | No; the instance can still be shared after creation |
| **request** | One instance tied to an HTTP request in a web context | Does not protect if the instance is passed to multiple threads or shared via async |
| **session** | One instance tied to an HTTP session | No; one session can have multiple concurrent requests |

### Prototype Is Not a Per-Request Instance

A prototype bean requested from the container creates a new instance per resolution. However, if a singleton injects a prototype directly via its constructor, the singleton usually retains the prototype instance created at injection time; it does not automatically get a new instance on every method call.

If you need to create a prototype instance per usage, inject **ObjectProvider<T>** or an appropriate factory:

~~~java
@Service
public class JobCoordinator {

    private final ObjectProvider<JobContext> contexts;

    public JobCoordinator(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public void runJob() {
        JobContext context = contexts.getObject();
        context.execute();
    }
}
~~~

This snippet assumes **JobContext** is declared with prototype scope and has an `execute` method. The container creates the instance when **getObject()** is called. Cleanup of a prototype bean is not fully managed by the container like a singleton; if the object owns resources, the application must plan to close them.

### Request Scope Must Also Be Used Properly

A request-scoped bean can hold data tied to one HTTP request. However:

- It is not persistent storage across requests.
- If a request is processed via async threads or passes objects to another thread, you must understand context propagation and the request lifecycle.
- It does not solve concurrent access to the same database records.

### Session Scope Can Have Multiple Concurrent Requests

Users open multiple tabs or fire multiple nearly simultaneous requests within the same session. A session-scoped bean can be accessed by multiple requests at the same time. Thus, mutable state inside a session bean still needs synchronization design if concurrent access occurs.

**Changing scope only changes an object's lifecycle and sharing boundary. It does not replace thread-safety design.**

## 12. @Async and @Scheduled: Additional Threads Accessing Singletons

A service can be invoked from both request threads and background threads:

~~~java
@Service
public class NotificationService {

    private final EmailSender emailSender;

    public NotificationService(EmailSender emailSender) {
        this.emailSender = emailSender;
    }

    @Async
    public CompletableFuture<Void> sendAsync(String address) {
        emailSender.send(address);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

When **@EnableAsync** is enabled and the method is called through the Spring proxy, work can be dispatched to an executor. Concurrent invocations may still use the same **NotificationService** singleton. If the service stores mutable per-email fields, concurrent runs can overwrite each other's data.

Similarly:

~~~java
@Component
public class DailyJob {

    @Scheduled(fixedRate = 60_000)
    public void run() {
        // Periodic task.
    }
}
~~~

The scheduler invokes the method on a schedule. If a job runs longer than its interval or multiple application instances exist, you need to understand scheduler configuration and how jobs are triggered. Do not assume simply marking a method **@Scheduled** makes all executions sequential system-wide.

### @Async Is Not a Cure for Race Conditions

Running asynchronously can increase parallelism, which creates even more concurrent invocations. If tasks share a singleton with mutable state, the risk of race conditions increases.

Pass task data via parameters or immutable command objects:

~~~java
@Async
public CompletableFuture<Void> sendAsync(
        NotificationCommand command) {
    emailSender.send(command.address(), command.message());
    return CompletableFuture.completedFuture(null);
}
~~~

Do not store **currentAddress** or **currentMessage** in singleton fields before sending.

## 13. @Transactional Does Not Make Singleton Fields Thread-Safe

Another misconception is: if a service method has **@Transactional**, all operations inside the bean are safe when called by multiple threads. That is false.

Transactions generally manage operation boundaries with resources like databases via a transaction manager. They do not automatically lock Java fields inside a singleton bean:

~~~java
@Service
public class UnsafeSequenceService {

    private int nextNumber;

    @Transactional
    public int next() {
        return ++nextNumber;
    }
}
~~~

Two transactions can call **next()** on the same object simultaneously and update the **nextNumber** field concurrently. A database transaction does not turn incrementing an `int` on the heap into an atomic operation.

If sequence numbers must be unique across multiple instances, a singleton field is also insufficient because each process has its own variable. Use a database sequence/identity, atomic updates, or a centralized numbering mechanism with suitable consistency.

**Transactions and thread safety address different scopes:**

- Transactions protect the consistency of operations on transactional resources.
- Locks/atomics/concurrent structures protect concurrent access to in-memory state within their scope.
- Database constraints/transactions/locking protect shared data across transactions and processes using database mechanisms.

## 14. Synchronization Within One JVM Differs from Synchronization Across Instances

Example:

~~~java
private final AtomicInteger counter = new AtomicInteger();
~~~

This variable is safe for threads accessing **the instance containing it**. However, when the application runs across three servers, each server has its own `AtomicInteger`:

~~~text
Server A: counter = 10
Server B: counter = 10
Server C: counter = 10
~~~

Incrementing the counter on Server A does not change the variable on B or C. **synchronized**, **ReentrantLock**, **AtomicInteger**, and **ConcurrentHashMap** in process memory do not create distributed synchronization.

When state is shared across multiple instances, you can use:

- A database with transactions, unique constraints, optimistic/pessimistic locking, or atomic updates.
- Redis or a shared storage system with appropriate synchronization primitives.
- A message broker/queue to serialize processing by key or partition when the model allows.
- Distributed locks with leases, timeouts, disconnect handling, and fencing tokens if distributed locking is truly needed.

Do not pick a distributed lock solely because the application has multiple servers. Sometimes database transactions or constraints are simpler and more reliable. Start from the invariants to protect and pick the mechanism matching the resource actually being shared.

## 15. How to Identify the Right Solution

| Requirement | Approach to consider |
|---|---|
| Service only computes from inputs and immutable dependencies | Stateless service |
| Shared configuration unchanged after startup | Immutable configuration object, `final` dependencies |
| Simple start/stop flag between threads | `volatile` or `AtomicBoolean` |
| Simple counter in one JVM | `AtomicInteger`/`AtomicLong` |
| High-update-frequency statistics counter | `LongAdder` |
| Updating multiple fields together | `synchronized` or `Lock` |
| Map shared by multiple threads | `ConcurrentHashMap`, while designing compound operations |
| Data specific to a single request | Local variables/command objects/appropriate request scope |
| State that must survive restarts | Database or persistent storage |
| State shared across multiple processes | Database/cache/message broker with suitable coordination |

No single annotation turns every class into a thread-safe component. The solution must come from **what state is shared, which operations must be atomic, and the scope of threads/processes that can access it**.

## 16. Practical Example: Fixing a Counter in a Singleton

Suppose there is a service:

~~~java
@Service
public class RequestCounter {

    private int total;

    public int increment() {
        total++;
        return total;
    }

    public int getTotal() {
        return total;
    }
}
~~~

If 20 threads each call **increment()** 1,000 times, the expected total is 20,000. Because **total++** is not atomic, the result can be smaller. Faulty outcomes depend on execution scheduling, so an occasional run might happen to produce the right number.

### AtomicInteger Option

~~~java
@Service
public class RequestCounter {

    private final AtomicInteger total = new AtomicInteger();

    public int increment() {
        return total.incrementAndGet();
    }

    public int getTotal() {
        return total.get();
    }
}
~~~

Within one JVM, increments on the same `AtomicInteger` will not lose updates.

### synchronized Option

~~~java
@Service
public class RequestCounter {

    private int total;

    public synchronized int increment() {
        return ++total;
    }

    public synchronized int getTotal() {
        return total;
    }
}
~~~

Both reads and writes use the same monitor. If only `increment` is synchronized while `getTotal` reads without synchronization or another visibility mechanism, reads remain unprotected as intended by the design.

### Concurrency Test Sketch

You can use **ExecutorService**, **CountDownLatch**, and JUnit to launch multiple tasks, wait for all to complete, and check the total:

~~~java
int threadCount = 20;
int incrementsPerThread = 1_000;

ExecutorService executor =
        Executors.newFixedThreadPool(threadCount);
CountDownLatch start = new CountDownLatch(1);
CountDownLatch done = new CountDownLatch(threadCount);

for (int i = 0; i < threadCount; i++) {
    executor.submit(() -> {
        try {
            start.await();
            for (int j = 0; j < incrementsPerThread; j++) {
                counter.increment();
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        } finally {
            done.countDown();
        }
    });
}

start.countDown();
done.await();
executor.shutdown();

assertEquals(
        threadCount * incrementsPerThread,
        counter.getTotal());
~~~

This is an illustrative test body; you must initialize **counter** first, add JUnit/concurrency imports, and handle timeouts/shutdown appropriately in real tests. Concurrency tests can help uncover bugs, though a single passing run does not prove all interleavings are safe. For race conditions, understand the synchronization mechanism and use repeated testing or specialized tools when risk is high.

## 17. Common Mistakes

### Assuming Singletons Are Thread-Safe by Default

Spring singleton only specifies scope. A singleton bean holding an **ArrayList**, **HashMap**, or mutable field can still be accessed concurrently by multiple threads.

### Switching ArrayList to Vector or synchronizedList and Stopping There

Synchronized collections protect certain individual operations, yet a sequence like **if (!list.contains(x)) list.add(x)** may still require a shared critical section. Additionally, a thread-safe collection does not guarantee the data belongs to the right user.

### Putting Request Data into Service Fields

Fields like **currentUser**, **currentOrder**, or **currentRequest** in a singleton can be overwritten by another request. Pass data through parameters or per-request objects.

### Using volatile for Variable Increments

`volatile` helps with visibility, not making **count++** atomic. Use `AtomicInteger` or a lock when lossless updates are needed.

### Using synchronized Inconsistently Across Locks

If method A locks **this** while method B locks another object, they do not protect the same state. Every read/write path for an invariant must follow the same mechanism.

### Holding Locks During External System Calls

A slow HTTP call inside a `synchronized` block can hold the lock for a long time, making many threads wait and degrading throughput. Narrow the critical section and avoid calling uncontrolled code while holding a lock.

### Using Local Locks to Protect Distributed Data

Locks in one JVM do not coordinate with other processes. If multiple instances modify the same database record, you need database-level mechanisms or distributed coordination.

### Assuming @Transactional Protects Every Field

A transaction is not a Java object monitor. Mutable fields in a singleton still need atomics/locks or redesign.

### Assuming Request/Session Scope Is Automatically Thread-Safe

One session can have multiple concurrent requests. Request-scoped objects can be passed into async executions. Scope does not automatically resolve all cross-thread access.

## 18. Design Principles for Singleton Beans

**Keep services stateless whenever possible.** Use `final` fields for dependencies and local variables for per-invocation data.

**Prefer immutable objects.** Immutable configurations, policies, and value objects are easier to share than mutable objects.

**If mutable state is needed, define invariants first.** Clearly specify which conditions must always hold and which operations must be treated as a single unit.

**Choose synchronization primitives matching the operation.** Atomics for simple updates, locks for compound operations, concurrent collections for shared data structures.

**Separate user state from singleton services.** Use a database/cache or a context with an appropriate lifecycle.

**Consider all concurrent call sources.** HTTP, `@Async`, schedulers, listeners, and callbacks can all produce concurrent access.

**Distinguish in-process from cross-process.** In-heap atomics/locks do not replace transactions or data-sharing mechanisms across multiple servers.

**Do not rely on manual testing to conclude thread safety.** Race bugs may only surface under load, on a specific runtime, or under rare interleavings.

## Conclusion

**Spring's singleton scope does not equate to thread safety.** A singleton bean is typically shared by multiple requests and background tasks within the same `ApplicationContext`. If the bean holds mutable state without synchronization, multiple threads can cause race conditions, lost updates, or visibility bugs.

The preferred design direction is **stateless services, immutable dependencies, and per-invocation data kept in local variables or dedicated objects**. When shared state is truly needed, select Atomic classes, `synchronized`/`Lock`, or concurrent collections according to the operation type and invariants to protect. If data is shared across multiple processes, storage-layer mechanisms or distributed coordination are required.

Spring is responsible for managing bean lifecycles and provisioning; **the developer is responsible for designing state and concurrency safety in bean code**. Maintaining that clear boundary keeps Spring Boot applications stable under multiple requests, threads, and instances.
