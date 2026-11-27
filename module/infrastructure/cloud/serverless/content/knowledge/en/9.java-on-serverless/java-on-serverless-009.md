# Managing Concurrency and Shared State Safety

A Java serverless application can spin up many execution environments to handle rising load. Each environment has its own JVM, memory, and lifecycle; some platforms also allow multiple requests or invocations to run concurrently within the same instance. Inside a single invocation, code may also spawn threads or run tasks in parallel. Consequently, shared state can be accessed concurrently across multiple distinct scopes.

A `static` field in Java can persist across multiple calls on the same JVM, yet is never shared across function instances and is never guaranteed to survive long term. A `synchronized` lock can protect data among threads inside one JVM, yet cannot lock another instance. Confusing these scopes can lead to overwritten data, double-deducted inventory, concurrent processing of the same event, or data from one request leaking into the next.

This lesson distinguishes concurrency within a single JVM from concurrency across multiple function instances, helps you choose appropriate state-management mechanisms, and shows how to design safe Java handlers under scale.

## Learning objectives

After this lesson, you will be able to:

- Explain execution environment lifecycles and the effect of warm reuse on static variables.
- Distinguish JVM-local state from shared cross-instance state.
- Identify race conditions, visibility issues, and non-atomic updates in Java.
- Choose among immutable state, atomic operations, optimistic locking, pessimistic locking, and distributed coordination.
- Design idempotency to protect side effects when events or requests are reprocessed.
- Safely reuse clients while bounding threads and connections inside functions.
- Test for race conditions and observe resource contention in serverless environments.

## 1. Concurrency exists across multiple scopes

In FaaS, a single function's logic can execute across many independent environments. As load increases, the platform scales out execution environments or instances according to service scaling rules.

~~~mermaid
flowchart TD
    A["HTTP / Queue / Event"] --> B["FaaS platform"]
    B --> C["JVM instance A"]
    B --> D["JVM instance B"]
    B --> E["JVM instance C"]
    C --> F["Database / Shared service"]
    D --> F
    E --> F
~~~

Each JVM has its own heap, static fields, threads, and objects. Multiple instances concurrently accessing a database or Redis create system-wide concurrency even if each JVM processes only one invocation at a time.

Concurrency scopes fall into three layers:

| Scope | Example | Appropriate protection mechanism |
|---|---|---|
| Multiple threads within one JVM | Two threads mutating the same HashMap | `synchronized`, locks, concurrent collections, atomic classes |
| Multiple invocations within one instance | Runtime permits concurrent requests or handler runs parallel tasks | Thread-safe objects, bounded internal concurrency, no global request state |
| Multiple function instances or services | Two JVMs updating one product or processing the same event | Database transactions, unique constraints, atomic operations in shared stores, distributed coordination |

Never assume all FaaS platforms share the same concurrency model. With standard AWS Lambda execution environments, each environment handles one invocation at a time; other compute options or runtimes follow different concurrency models. Some container/function platforms also permit multiple concurrent requests per instance. Even when a runtime serializes invocations, Java code can still spawn multiple threads, and multiple environments can still update the same backend data concurrently. Verify the concurrency model of your exact compute type and configuration.

## 2. Warm reuse and static variables in Java

Platforms can reuse an execution environment after an invocation completes. The JVM and initialized objects remain in memory, lowering initialization cost on subsequent calls. This is commonly referred to as **warm reuse**.

Example:

~~~java
public final class RequestCounter {
    private static long count = 0;

    public long handle() {
        count++;
        return count;
    }
}
~~~

If the same JVM is reused, count may keep incrementing across invocations. However, that value:

- Is not shared with other JVMs.
- Is lost when the platform reclaims the environment.
- Resets when new instances are created.
- Cannot serve as a business counter or system of record.
- Can suffer race conditions if accessed by multiple threads.

Static fields are therefore suited for immutable configuration or properly initialized shared clients. Business state such as balances, inventory, order status, event processing counts, and workflow progress belongs in durable storage services.

### What can and should not live in static fields

| Data kind | Keep in static field? | Notes |
|---|---|---|
| Parsed, immutable configuration | Yes | Never mutate after initialization; hold no request-specific data |
| Thread-safe SDK clients | Conditional | Verify client documentation; manage timeouts and connections |
| Configured ObjectMapper | Conditional | Never mutate configuration while in use |
| Reconstructible local cache | Conditional | Per-instance optimization only; enforce TTL and memory limits |
| Current request's user ID or tenant ID | No | Risks leaking data across requests |
| Order status or account balance | No | Must live in a database or durable state store |
| System-wide accurate counters | No | Use atomic operations or a shared data store |

A JVM-local cache can help hold rarely changing metadata, but must never be treated as a shared cache. When a shared cache across instances is needed, use an external cache and design TTLs/invalidation explicitly as part of the architecture.

## 3. Race conditions and the Java Memory Model

A **race condition** occurs when outcomes depend on uncontrolled execution ordering across threads or processes. A classic example is incrementing a variable:

~~~java
count++;
~~~

Incrementing is not a single atomic operation. Conceptually, it reads the value, adds one, and writes it back. If two threads both read 10 before writing, both write 11; one increment is lost.

### Visibility and atomicity

The Java Memory Model defines when writes made by one thread become visible to another. Distinguish two concerns:

- **Atomicity:** whether an operation executes as an indivisible unit without interleaving.
- **Visibility:** whether a write performed by one thread is observed in a timely manner by another thread.

`volatile` guarantees visibility and certain ordering constraints for a variable, but does not make read-modify-write operations like `count++` atomic. `synchronized` or locks establish mutual exclusion among threads sharing the same lock inside one JVM. They do not coordinate across multiple JVMs.

Thread-safe counter example within one JVM:

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class LocalInvocationMetrics {
    private final AtomicLong completed = new AtomicLong();

    public long markCompleted() {
        return completed.incrementAndGet();
    }

    public long currentValue() {
        return completed.get();
    }
}
~~~

AtomicLong protects increments inside one JVM. Across 10 function instances, each holds its own LocalInvocationMetrics; their individual counts are not a global system counter. For accurate business counters, use atomic counters in a database, Redis, or a dedicated service with appropriate semantics.

### HashMap is unsafe for concurrent mutation

If multiple threads write concurrently to a HashMap, entries can be lost or internal map structures can enter undefined states. Use ConcurrentHashMap when a map must be shared across threads in one JVM:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public final class LocalLookup {
    private final ConcurrentMap<String, String> values =
            new ConcurrentHashMap<>();

    public String getOrLoad(String key) {
        return values.computeIfAbsent(key, this::load);
    }

    private String load(String key) {
        return "value-for-" + key;
    }
}
~~~

ConcurrentHashMap solves only intra-process concurrent access. It does not share maps across execution environments, nor does it provide TTLs, business eviction policies, or cross-instance invalidation. For real local caches, bound size and data age.

## 4. Request state must have an explicit scope

A subtle bug is storing request details in a singleton field or static variable:

~~~java
public final class UnsafeHandler {
    private String currentTenant;

    public String handle(String tenantId) {
        currentTenant = tenantId;
        // Business processing may call multiple services.
        return currentTenant;
    }
}
~~~

If the runtime allows two requests to execute concurrently on the same object, the second request can overwrite currentTenant while the first is still running. The first request then accesses the wrong tenant's data.

Pass request data via parameters or a dedicated per-invocation context object:

~~~java
public record RequestContext(
        String requestId,
        String tenantId,
        String actorId) {
}

public final class SafeOrderService {
    public OrderResult handle(
            RequestContext context,
            CreateOrderCommand command) {
        // Use this invocation's context; never store in a shared field.
        return createForTenant(context.tenantId(), command);
    }

    private OrderResult createForTenant(
            String tenantId,
            CreateOrderCommand command) {
        // Call repository with the verified tenant.
        return new OrderResult(command.orderId(), "ACCEPTED");
    }
}

public record CreateOrderCommand(String orderId) {
}

public record OrderResult(String orderId, String status) {
}
~~~

If using ThreadLocal to bind context to a thread, remember that threads may be reused. Always remove the value inside a finally block once processing ends. For async code, ThreadLocal also does not automatically cross thread boundaries; use proper context propagation instead of assuming request context stays attached to the thread.

## 5. Choosing synchronization by where state lives

No single lock covers every scope. Choose mechanisms based on where data resides and business semantics.

| Mechanism | Scope | Best suited when | Limitations |
|---|---|---|---|
| `synchronized` / ReentrantLock | One JVM | Protecting in-process objects or data structures | Does not lock other instances; locks vanish on process exit |
| Atomic classes | One JVM | Simple counters or single-variable updates | Not a multi-field or multi-instance transaction |
| Database optimistic locking | Multiple processes updating a record | Conflicts are infrequent and retries are feasible | Requires handling conflicts and bounded retries |
| Database pessimistic locking | Multiple transactions | Must lock a record during a short transaction | Can cause waits, deadlocks, and reduced throughput |
| Atomic operations in Redis or DB | Multiple instances | Counters, set-if-absent, conditional updates | Must understand durability, expiry, and command semantics |
| Distributed lock | Multiple instances | Coordinating exclusive work when simpler options fail | Requires leases, fencing, client-crash handling, and partition tolerance |

### Optimistic locking

Optimistic locking assumes conflicts are rare. Records carry a version column; an update transaction succeeds only if the version still matches the value originally read. If another invocation updated the record first, the current operation fails to update and must reload or retry.

JPA example:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class InventoryItem {
    @Id
    private String productId;

    private int available;

    @Version
    private long version;

    protected InventoryItem() {
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (available < quantity) {
            throw new InsufficientInventoryException();
        }
        available -= quantity;
    }

    public int getAvailable() {
        return available;
    }
}

class InsufficientInventoryException extends RuntimeException {
}
~~~

At transaction commit, the JPA provider checks the version. If the row changed, it throws OptimisticLockException. The application must handle the conflict at the transaction boundary: reload current state, check whether stock suffices, and perform bounded retries. Never retry infinitely, which amplifies load during heavy contention.

### Pessimistic locking

Pessimistic locking locks rows inside a transaction, such as via `SELECT ... FOR UPDATE`. Other invocations needing the same row wait or time out.

This fits high-contention scenarios requiring consistent read-modify-write sequences. Keep transactions as short as possible; never call payment APIs or wait on external networks while holding database locks. Long transactions cause lock contention and deadlocks that degrade overall throughput.

### Atomic updates at the data source

For straightforward mutations, a conditional update can be safer and more efficient than a separate read followed by a write:

~~~sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE product_id = :product_id
  AND available >= :quantity;
~~~

If the affected row count is 1, stock was reserved cleanly. If 0, either the product does not exist or stock was insufficient at update time; a follow-up read distinguishes those two cases. Because condition and update execute atomically in one statement, two invocations cannot consume the same remaining stock.

## 6. Concurrency across multiple function instances

Suppose two invocations simultaneously process orders for the last remaining unit of a product:

1. Instance A reads available = 1.
2. Instance B reads available = 1.
3. A checks stock is sufficient.
4. B also checks stock is sufficient.
5. A writes available = 0.
6. B writes available = 0.

Both orders can be confirmed even though only one unit existed. This is a lost update. A Java lock inside A cannot block B because the two instances run in separate JVMs.

Place coordination close to the authoritative data store:

- Use conditional updates or optimistic/pessimistic locking in the database.
- Use atomic decrements or scripts in Redis when that store genuinely owns quota/inventory with matching durability requirements.
- Use transactions for multi-record updates requiring atomicity.
- Use queues or partition keys to serialize work sharing the same business key when traffic patterns allow.
- Use idempotency keys to prevent the same business request from applying side effects multiple times.

Never use static locks or synchronized blocks to protect resources shared across instances. They synchronize only within a single JVM.

### Distributed locks require fencing and leases

Distributed locks help when only one instance may perform a task at a time. However, a lock lease can expire while the previous holder is still running—for instance, due to a long GC pause or network hiccup. A new client acquires the lock and starts working; the stalled client recovers and resumes writing. At that moment, two clients act concurrently even though the lock service issued only one active lease.

For critical resources, pair locks with **fencing tokens** or monotonically increasing versions. Every lock acquisition returns a higher token; the data store accepts writes only if the token exceeds the last recorded token. Thus, a stale client with an older token cannot overwrite newer work.

Whenever conditional writes or transactions at the data source itself solve the problem, prefer that simpler approach over building distributed locks. Introduce locks only for explicitly identified race conditions.

## 7. Idempotency protects operations under retries and concurrency

Serverless systems commonly deliver messages with at-least-once semantics across many trigger types. A client request can time out after the function completes; a message can be redelivered; two producers can even submit the same business request nearly simultaneously.

**Idempotency** ensures multiple deliveries of the same request yield a business outcome equivalent to processing it once.

A common pattern pairs a stable idempotency key with a database unique constraint:

~~~sql
CREATE TABLE processed_request (
    idempotency_key VARCHAR(120) PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    result_json TEXT,
    created_at TIMESTAMP NOT NULL,
    lease_until TIMESTAMP,
    owner_token VARCHAR(120)
);
~~~

Processing flow:

1. Receive request and validate the idempotency key.
2. Attempt to insert a record with that key.
3. If the key already exists with status SUCCEEDED, return the stored result.
4. If the key is currently PROCESSING, apply a wait policy, return an in-progress status, or reschedule.
5. If inserting the key succeeds, execute the business logic within an appropriate transaction.
6. Persist the result and mark SUCCEEDED before returning success.

Coordinate claiming the key and updating business data inside the same transaction when sharing one database. For PROCESSING states, store lease_until and owner_token so another worker can take over if the lease expires; takeover must use a conditional update so two workers cannot claim ownership together. When business logic calls external services beyond the database, use that service's idempotency key and outbox/saga patterns as needed. Never mark SUCCEEDED before side effects complete.

Idempotency and concurrency control answer different questions: idempotency prevents duplicating the exact same request; optimistic locking or atomic updates protect when distinct requests contend for the same resource.

## 8. Reusing clients and bounding concurrency in Java functions

Creating SDK clients, connection pools, or ObjectMappers per invocation increases cold-start overhead and connection counts. You can reuse objects at class scope when:

- The object is fully configured before sharing.
- Documentation confirms the object/client is thread-safe.
- No per-request data is stored inside the object.
- Connection pools and timeouts are bounded to match downstream capacity.

Example:

~~~java
public final class CatalogHandler {
    private static final CatalogClient CLIENT =
            CatalogClient.createFromEnvironment();

    public CatalogResult handle(CatalogRequest request) {
        return CLIENT.lookup(request.productId());
    }
}
~~~

CatalogClient here is an illustrative client; reuse it like this only when the real library supports concurrent cross-thread use. Not every SDK client or custom client is thread-safe.

### Never spawn unbounded threads

If an invocation receives a batch of 500 items and spawns 500 threads, the function can exhaust memory, file descriptors, connection pools, or downstream quotas. Use a bounded executor and await completion before the handler returns.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;

public final class BoundedBatchProcessor {
    private final ExecutorService executor;

    public BoundedBatchProcessor(ExecutorService executor) {
        this.executor = executor;
    }

    public List<String> process(List<String> items) {

        List<Future<String>> futures = new ArrayList<>();
        for (String item : items) {
            futures.add(executor.submit(() -> processOne(item)));
        }

        // Return results only after all tasks finish.
        List<String> results = new ArrayList<>(futures.size());
        try {
            for (Future<String> future : futures) {
                results.add(getResult(future));
            }
            return results;
        } catch (RuntimeException failure) {
            // Request cancellation of remaining tasks if the batch cannot finish.
            futures.forEach(future -> future.cancel(true));
            throw failure;
        }
    }

    private String getResult(Future<String> future) {
        try {
            return future.get();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Processing interrupted", ex);
        } catch (ExecutionException ex) {
            throw new IllegalStateException("Item processing failed", ex.getCause());
        }
    }

    private String processOne(String item) {
        return "processed:" + item;
    }
}
~~~

The executor is injected so the composition root can configure bounded thread counts and task queues, for example:

~~~java
ExecutorService executor = new ThreadPoolExecutor(
        8, 8, 0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(64),
        new ThreadPoolExecutor.CallerRunsPolicy());
~~~

Corresponding imports are ArrayBlockingQueue, TimeUnit, ThreadPoolExecutor, and ExecutorService. The executor's owner is responsible for shutting it down per runtime lifecycle; if the platform offers no suitable lifecycle hook, you may create a per-invocation executor, shut it down, and await completion before returning, factoring in initialization cost. Always enforce timeouts on tasks, bound database/API request rates, and define per-item failure reporting. Never allow background threads to continue writing data after the handler returns or after invocation timeout.

When processing a batch in parallel, completion order may differ from input order. For FIFO or order-sensitive workflows, parallelize only independent items or shard by message group. When an item fails, collect failures and return partial batch responses matching the trigger contract.

## 9. Resource limits and backpressure

Scaling functions faster than databases or downstream APIs can handle leads to overload. Each instance may maintain its own connection pool; if 100 instances open pools of up to 20 connections, the backend could face up to 2,000 connections.

Coordinate limits across layers:

- **Function concurrency:** cap maximum concurrent invocations.
- **Executor size:** bound internal threads per invocation.
- **Connection pools:** bound per-instance connections and projected fleet totals.
- **Rate limits:** cap request rates to external APIs.
- **Queue buffering:** absorb bursts in queues and drain at a backend-sustainable pace.
- **Timeouts and backpressure:** reject new work when safe capacity is exhausted.

With queues, queue depth and oldest message age signal when to tune concurrency. With HTTP triggers, return retryable errors or overload responses per the API contract instead of holding requests indefinitely.

## 10. Testing concurrency and observing production

Sequential unit tests miss many race conditions. Test the same key or record concurrently across multiple threads, invocations, and function instances.

| Scenario | How to test | What to verify |
|---|---|---|
| Two threads incrementing the same counter | Use CountDownLatch to release threads simultaneously | Atomic counter yields exact sum |
| Two invocations claiming the last item | Send two distinct requests concurrently | Only one request succeeds |
| Duplicate event | Send identical eventId concurrently | Only one business side effect executes |
| Two tenants sharing a handler | Interleave and parallelize requests | Zero cross-tenant/request context leakage |
| Local caches across instances | Invoke multiple distinct instances | No reliance on static fields for synchronization |
| Cache/database outage | Inject timeouts and connection failures | Bounded fallbacks without retry storms |
| Function timeout while task runs | Simulate slow task past invocation budget | No uncontrolled background writes remain |

In Java, use CountDownLatch, CyclicBarrier, or stress tools to force threads into contending on the same target. Integration tests should fire concurrent invocations against production-like environments and assert final database state rather than checking HTTP responses alone.

Metrics to monitor:

- Concurrent invocation counts and active execution environments.
- Processing duration, timeouts, throttling, and cold starts.
- Thread counts, task queue depth, and executor rejections.
- Connection pool active/idle counts, timeouts, and connection errors.
- Optimistic lock conflicts, deadlocks, and transaction retries.
- Duplicate events, idempotency hits, and suppressed side effects.
- Queue depth, message age, and redelivery counts.

Logs must carry request ID, correlation ID, business key, and function version for tracing. Never log tokens, secrets, or unnecessary personal data.

## 11. Shared state management checklist

- [ ] FaaS provider concurrency model and multi-request-per-instance capability are verified.
- [ ] Static fields contain only immutable configuration or verified thread-safe shared clients.
- [ ] No tenant, user, request, or business state is stored in shared fields.
- [ ] Local caches enforce size limits and TTLs and are never treated as sources of truth.
- [ ] `synchronized`, `volatile`, and `AtomicLong` are never used to lock/coordinate state across multiple instances.
- [ ] Shared data is protected in a database or service with appropriate atomic operations.
- [ ] Optimistic/pessimistic locking or conditional updates guard contended resources.
- [ ] Stable idempotency keys and unique constraints guard re-deliverable requests.
- [ ] Thread pools, connection pools, timeouts, and concurrency are bounded.
- [ ] Async tasks complete or are explicitly managed before invocation ends.
- [ ] Backpressure and load caps protect downstream dependencies.
- [ ] Race conditions, duplicates, timeouts, outages, and interleaved multi-tenant requests are tested.
- [ ] Metrics track lock conflicts, connections, retries, concurrency, and queue age.

## Self-check

1. Why can a static variable retain its value after an invocation yet still fail as durable state for a serverless function?
2. What problem does `volatile` solve, and why does it not make `count++` atomic?
3. Why does `synchronized` fail to protect inventory when two separate function instances update the database concurrently?
4. When should you use optimistic locking versus pessimistic locking?
5. How does idempotency differ from concurrency control?
6. Why should you avoid spawning one thread per message in a large batch?
7. If 100 function instances all fall back directly to the database when Redis fails, what problem can the system experience?
8. Besides current state, what data should be retained to investigate a race condition in production?

Java serverless applications must be designed like distributed systems: each execution environment has isolated memory, an ephemeral lifecycle, and can execute concurrently alongside many other instances. Keep request state scoped to each invocation, use immutable or thread-safe objects for intra-JVM sharing, and anchor business guarantees in databases or shared services with atomic semantics. Combining idempotency, concurrency bounds, backpressure, and concurrent testing lets functions scale while preserving data integrity.
