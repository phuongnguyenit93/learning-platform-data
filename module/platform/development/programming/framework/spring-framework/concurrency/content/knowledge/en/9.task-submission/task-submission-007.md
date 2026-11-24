# Capturing Appropriate Input Data Before Handing Off to Another Thread

In a **Spring Framework - concurrency** application, an HTTP request may receive input, call a service, and then hand off part of the work to an **Executor**, **@Async**, or **CompletableFuture**. At handoff time, the other thread may not have started running yet; it might not even run until after the HTTP request has finished. If the asynchronous task continues referencing data that **can mutate, be freed, or fall out of valid scope**, results become unstable and there is a risk of leaking data across requests.

The core principle of **"Capturing Appropriate Input Data Before Handing Off to Another Thread"** is: **identify precisely what data the task needs, take an appropriate snapshot at handoff time, define who owns that copy, and prevent the sender from continuing to modify parts the task must treat as immutable**.

This lesson belongs to the **Task Submission and Retrieval** group. It does not demand blindly cloning every object: "appropriate" means **sufficient data, proper lifecycle, immutability where required, no unnecessary secrets, and proper error/resource-limit handling**.

## 1. The Boundary Between the Request Thread and the Worker Thread

Suppose request A places an order:

~~~text
HTTP request thread
  |
  | 1. Read payload, principal, requestId
  | 2. Validate and normalize data
  | 3. Create snapshot for the task
  | 4. executor.submit(() -> process(snapshot))
  |
  +-------------------------------> Worker thread
  |                                    |
  |                                    | 5. May run later
  |                                    | 6. Use received snapshot
  |                                    v
  +--> HTTP request ends           Process result
~~~

Two threads do not share a default "shared local variable region". When passing an object into a lambda or asynchronous method, Java normally passes **the reference value to the object**, without automatically cloning the entire object graph. If sender and receiver both point to the same **ArrayList**, **HashMap**, or DTO with setters, they can observe each other's modifications.

In other words:

- **Handoff**: the executor accepts a Runnable/Callable, or the Spring proxy routes an @Async method to a TaskExecutor.
- **Data capture**: the application decides which values are copied, which new objects are created, and what level of immutability must be guaranteed.
- **Task execution**: the worker uses the values it received; the worker should not assume the caller's request, session, transaction, or ThreadLocal still exists.
- **Result retrieval**: Future/CompletableFuture reports the job's state, without automatically making the inputs the task read safe.

## 2. Lambda "Variable Capture" Is Not a "Data Snapshot"

Consider this code:

~~~java
List<String> items = new ArrayList<>();
items.add("book");

executor.execute(() -> process(items));

items.add("pen");
~~~

This is an **illustrative code snippet** (assuming imports, executor, and process exist). The lambda holds a reference to the exact same **List**. The local variable items is never reassigned so it satisfies **effectively final**, yet **the ArrayList object itself remains mutable**. The worker may read the list after pen is added, before pen is added, or encounter thread-safety issues if both sides read/write without synchronization.

Do not claim the task "received [book]" merely because the **execute** call happens before the **items.add** line. The effectively final rule only restricts **reassigning the captured variable**, not freezing the state of the object the variable points to.

Adding **final** does not solve it either:

~~~java
final List<String> items = new ArrayList<>();
items.add("book");
// items = new ArrayList<>(); // Cannot be reassigned.
items.add("pen");             // Can still mutate the object!
~~~

There are two separate questions:

| Scenario | Can the reference be changed? | Can the inner data be changed? |
| --- | --- | --- |
| Effectively final local variable pointing to ArrayList | Cannot reassign within capture scope | **Yes** |
| Final field pointing to HashMap | Cannot reassign the field | **Yes** |
| Record containing a mutable List | Cannot reassign the component | **Yes**, if the List remains mutable |
| Record containing List.copyOf of String | Cannot reassign the component | The List cannot be mutated directly; Strings are also immutable |
| DTO containing mutable nested objects | Depends on declarations | **Possibly**, needs a deeper snapshot |

Therefore, the question is not "is the parameter final?" but **"can any data the worker needs to read still be mutated through another reference?"**.

## 3. Java 17 Example: Worker Reads Wrong Data Because Reference Was Mutated

The following standalone example intentionally captures a **reference**, not a value snapshot. We use **CountDownLatch** to create a deterministic scenario: the worker has received the input, but must wait for the caller to finish mutating it before reading.

Save as **CapturedReferenceDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CapturedReferenceDemo {
    static final class MutableRequest {
        String owner = "An";
        final List<String> tags =
                new ArrayList<>(List.of("standard"));
    }

    public static void main(String[] args) throws Exception {
        MutableRequest request = new MutableRequest();
        ExecutorService executor = Executors.newSingleThreadExecutor();

        CountDownLatch workerReady = new CountDownLatch(1);
        CountDownLatch allowRead = new CountDownLatch(1);

        try {
            Future<String> result = executor.submit(() -> {
                workerReady.countDown();
                allowRead.await();
                return request.owner + " " + request.tags;
            });

            if (!workerReady.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker did not start within test timeout");
            }

            request.owner = "Bình";
            request.tags.add("urgent");
            allowRead.countDown();

            System.out.println("Worker read: "
                    + result.get(5, TimeUnit.SECONDS));
        } finally {
            allowRead.countDown();
            executor.shutdownNow();
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CapturedReferenceDemo.java
java CapturedReferenceDemo
~~~

**Stdout**, assuming the worker starts within the test timeout:

~~~text
Worker read: Bình [standard, urgent]
~~~

**Step-by-step explanation:**

1. The worker holds a reference to the same **MutableRequest** that the caller keeps.
2. The worker signals it started, then waits on **allowRead**.
3. The caller changes owner and adds a new tag, then opens the latch.
4. The worker reads **the current values after mutation**, not the values at submit time.
5. **CountDownLatch** establishes the required synchronization relationship, making the example deterministic. It avoids `Thread.sleep` to guess execution order.

This example deliberately simulates a design flaw. If the caller modifies an ArrayList while the worker iterates over it without synchronization, races or ConcurrentModificationException can also happen; however, **do not claim ConcurrentModificationException is guaranteed to occur**. Outcomes depend on scheduling and operation types.

## 4. Default Fix: Snapshot Before Submitting

Create an object **containing only the data needed for the job**, using immutable scalars and collection copies where appropriate. Take the snapshot **on the thread that owns the data**, **before** handing off the work, while the data is in a consistent state.

Save as **InputSnapshotDemo.java**, standalone runnable with Java 17:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class InputSnapshotDemo {
    static final class MutableRequest {
        String owner = "An";
        final List<String> tags =
                new ArrayList<>(List.of("standard"));
    }

    record JobSnapshot(String owner, List<String> tags) {
        JobSnapshot {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) throws Exception {
        MutableRequest request = new MutableRequest();

        // Snapshot created before submitting work to the executor.
        JobSnapshot snapshot =
                new JobSnapshot(request.owner, request.tags);

        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch workerReady = new CountDownLatch(1);
        CountDownLatch allowRead = new CountDownLatch(1);

        try {
            Future<String> result = executor.submit(() -> {
                workerReady.countDown();
                allowRead.await();
                return snapshot.owner() + " " + snapshot.tags();
            });

            if (!workerReady.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker did not start within test timeout");
            }

            request.owner = "Bình";
            request.tags.add("urgent");
            allowRead.countDown();

            System.out.println("Source data: "
                    + request.owner + " " + request.tags);
            System.out.println("Task snapshot: "
                    + result.get(5, TimeUnit.SECONDS));
        } finally {
            allowRead.countDown();
            executor.shutdownNow();
        }
    }
}
~~~

Compile and run commands:

~~~bash
javac -encoding UTF-8 InputSnapshotDemo.java
java InputSnapshotDemo
~~~

**Stdout** (when worker starts successfully):

~~~text
Source data: Bình [standard, urgent]
Task snapshot: An [standard]
~~~

Why is the fix safer?

- **owner** is an immutable String, so capturing the String reference value at snapshot time suffices.
- **List.copyOf(tags)** creates an unmodifiable collection, independent of subsequent additions/removals on the source ArrayList.
- The elements in the example are **String**, which are also immutable, leaving no mutable branches inside this List.
- The worker receives only **snapshot**, without holding the mutable **request** or re-reading the source state after handoff.
- The record guarantees component references do not change after construction; **defensive copying of the collection** guarantees the list contents cannot be altered through an alias.

**List.copyOf** is not "synchronization magic": if another thread is **concurrently modifying the source collection during snapshot creation**, the copy operation can yield inconsistent results or fail. To snapshot properly, you must first have **exclusive temporary ownership of the data**, use a **lock**, use **safely published immutable inputs**, or apply a suitable synchronization mechanism.

## 5. Shallow Copy vs. Deep Snapshot: Inspect the Entire Object Graph

The next mistake is creating a new list where each element is still the exact same mutable object.

~~~java
List<MutableLine> copied = List.copyOf(originalLines);
~~~

This is an **illustrative snippet**. Even though **copied** disallows adding/removing elements, if an existing **MutableLine** inside the list changes its price or SKU, the worker still observes **the mutated element object**.

A standalone example, saved as **NestedSnapshotDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NestedSnapshotDemo {
    static final class MutableLine {
        String sku;

        MutableLine(String sku) {
            this.sku = sku;
        }
    }

    record LineView(String sku) {
    }

    public static void main(String[] args) {
        MutableLine line = new MutableLine("SKU-01");
        List<MutableLine> source = new ArrayList<>();
        source.add(line);

        // Only creates an unmodifiable list; elements are still the original MutableLines.
        List<MutableLine> shallow = List.copyOf(source);

        // Capture only the needed data into a record containing String.
        List<LineView> deepEnough = source.stream()
                .map(item -> new LineView(item.sku))
                .toList();

        line.sku = "SKU-02";

        System.out.println("Shallow sees: " + shallow.get(0).sku);
        System.out.println("Snapshot sees: "
                + deepEnough.get(0).sku());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 NestedSnapshotDemo.java
java NestedSnapshotDemo
~~~

Stdout:

~~~text
Shallow sees: SKU-02
Snapshot sees: SKU-01
~~~

In the example, **deepEnough** is a "deep-enough snapshot" because the worker only needs the String field sku. It does not clone everything in the source object, only **the values meaningful to the task**.

Cases requiring extra thought:

| Source data | Typically appropriate capture | Notes |
| --- | --- | --- |
| String, enum, UUID | Keep retrieved value | These types are immutable |
| Primitive or immutable boxed types | Copy value | Choose the right read timing |
| List<String> | **List.copyOf(source)** | String elements are immutable; nulls are rejected |
| Set<String> | **Set.copyOf(source)** | Nulls are rejected; iteration order is not guaranteed to match source |
| Map<String, String> | **Map.copyOf(source)** | Keys/values cannot be null; keys/values should be immutable |
| List<MutableDTO> | Convert each element to a new immutable view/record | Copying the list alone is not enough |
| byte[] array | **Arrays.copyOf(source, source.length)** | Arrays are still mutable; do not share references if isolation is required |
| Map<String, List<MutableDTO>> | Snapshot map, lists, and each DTO as needed | Avoid aliasing across levels |
| JPA/Hibernate entities | Capture ID and needed fields, or reload in worker inside its own transaction | Do not carry persistence contexts or mutable entities across threads |
| Streaming data / MultipartFile | Capture durable content/path when sensible, bound sizes | File/stream lifecycle may end with the request |

**Records are not automatically deeply immutable.** A record such as **record Payload(List<MutableDTO> items)** still holds references to the list/elements unless the constructor defensively copies and elements are converted to suitable forms.

## 6. "Appropriate" Means Capturing Minimal, Well-Sourced Data

You do not need to copy the entire HTTP request or the entire domain object graph. Ask yourself:

1. What information does the worker **actually need** to complete the job? Often only requestId, userId, resource IDs, deadlines, and a few validated parameters.
2. Will the data **be mutated by the caller** after submission? Are there any mutable nested collections/DTOs?
3. Does the source data depend on **request scope, session, transaction, thread context, connections, or streams** that will expire before the worker uses it?
4. Is the data **sensitive**? Are you copying passwords, access tokens, or PII that the worker does not need?
5. If the worker runs **much later** or the task is retried, will the snapshot still be business-valid? Should the worker reload the latest state from the database?
6. Is the snapshot **too large** to hold inside an executor queue? Should it be replaced with an ID/reference to durable storage?

For example, a task sending an invoice notification email might only need:

~~~java
public record EmailJobInput(
        String requestId,
        long invoiceId,
        String recipientId,
        String templateKey
) {
}
~~~

This is a **standalone Java 17 record definition**, yet only a **sample snippet** without main. The worker can take invoiceId and load invoice details inside a separate transaction, instead of holding a JPA EntityManager alongside a large request object tree.

Conversely, if the requirement is "send the exact content the user confirmed at submit time", sending only an ID and re-reading data that **may have changed** is also wrong. In that case, capture a normalized immutable payload, a versioned snapshot, or persist a durable transaction record so the worker reads the exact version. **Choosing which data to snapshot is a business decision**, not merely a matter of Java syntax.

## 7. Java Memory Model: Visibility Does Not Replace Isolation

In Java, **ExecutorService** has an important memory consistency rule: actions in a thread prior to submitting a Runnable/Callable to an ExecutorService **happen-before** actions taken by that task; actions taken by the task happen-before subsequent steps after another thread returns successfully from **Future.get()**.

This helps **safely publish data prepared before submit** to the worker under the executor's contract. However:

- It **does not make an ArrayList thread-safe**.
- It **does not forbid** the caller from mutating inputs after submission.
- It **does not automatically clone** object graphs referenced by a lambda.
- It **does not guarantee** that a sequence of multiple fields read from a mutable source belongs to one consistent version if another thread writes concurrently.

Example:

~~~text
Caller: prepare list -> submit(task) -> mutate list
                           |
Worker:                read list (whenever scheduled)
~~~

The **before-submit → task** relation publishes earlier state; **mutating the list after submit** can race with the worker. Therefore, **snapshot + clear ownership** is the design solution, not just adding volatile or locking a single field.

If a task needs a "point-in-time snapshot" of multiple fields on an object that **another thread updates concurrently**, use a consistent strategy:

- Block mutations during copying with a **synchronized/Lock** shared with writers.
- Build a complete immutable object before publishing and **swap the entire reference** via a proper publication mechanism, rather than mutating fields individually.
- Read a **transaction snapshot** or versioned record from a data store with proper guarantees.
- **Transfer ownership** of the data to the worker with a guarantee the caller stops mutating it, if the protocol genuinely allows that.

Simply doing **new ArrayList<>(source)** while another thread is mutating source is not an atomic snapshot transaction.

## 8. Defensive-Copy Constructors: Both on Input and Output

A good structural pattern is a record or final class with explicit invariants:

~~~java
import java.util.List;
import java.util.Objects;

public record PriceJob(String orderId, List<Long> amounts) {
    public PriceJob {
        orderId = Objects.requireNonNull(orderId).strip();
        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId is empty");
        }
        amounts = List.copyOf(amounts);
    }
}
~~~

This is a **PriceJob.java file compilable when used by appropriate calling code**, not a program with main. It enforces non-null/non-empty **orderId** and copies the list. **Long** elements are immutable, so the data the worker reads is well isolated provided the caller owned the source when constructing the record.

Not every type only needs **List.copyOf**. With **byte[]**, even a final field can be mutated if the underlying array is returned directly. A class holding an array needs defensive copying in both constructor and accessor:

~~~java
import java.util.Arrays;

public final class BinaryPayload {
    private final byte[] bytes;

    public BinaryPayload(byte[] input) {
        this.bytes = Arrays.copyOf(input, input.length);
    }

    public byte[] bytes() {
        return Arrays.copyOf(bytes, bytes.length);
    }
}
~~~

This is a **standalone Java class without main**. If the getter returned bytes directly, external code could still modify the instance's data. For large payloads, copying cost must be weighed; consider durable file/blob storage referenced by ID with access control instead of copying large memory blocks per task.

**List.copyOf** and **Collections.unmodifiableList** are not identical. **Collections.unmodifiableList(source)** is typically a *view* that forbids modification through the view while still reflecting changes made to the backing list. **List.copyOf(source)** produces an independent collection unaffected by subsequent additions/removals on the source (assuming copied from a consistent source). Neither automatically turns mutable elements into immutable ones.

## 9. Spring MVC and @Async: Capturing the Snapshot at the Request Boundary

This is a very common scenario: a controller receives an HTTP request, knows the authenticated user, and invokes an async service. The right approach is **extracting needed values first**, constructing a snapshot object, passing it to the service, and letting the worker read only that copy.

The following files belong to a **Spring MVC application with Spring Web and Spring Context**, not plain javac examples. Each block is **a separate Java file** to place in the proper package.

**ReportJobInput.java** — snapshot for one task:

~~~java
package example.async;

public record ReportJobInput(
        String requestId,
        String userId,
        String title
) {
}
~~~

**ReportWorker.java** — service that does not store request inputs in instance fields:

~~~java
package example.async;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("reportExecutor")
    public CompletableFuture<String> build(ReportJobInput input) {
        String message = "done:" + input.requestId()
                + ":" + input.userId()
                + ":" + input.title();

        return CompletableFuture.completedFuture(message);
    }
}
~~~

**ReportController.java** — capturing the snapshot before the @Async boundary:

~~~java
package example.async;

import java.security.Principal;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ReportController {
    private final ReportWorker worker;

    public ReportController(ReportWorker worker) {
        this.worker = worker;
    }

    @PostMapping("/reports")
    public CompletableFuture<String> create(
            @RequestParam String title,
            Principal principal) {

        if (principal == null) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED);
        }

        String normalized = title.strip();
        if (normalized.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST);
        }

        ReportJobInput input = new ReportJobInput(
                UUID.randomUUID().toString(),
                principal.getName(),
                normalized
        );

        return worker.build(input);
    }
}
~~~

**AsyncConfig.java** — configuring a named executor:

~~~java
package example.async;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfig {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("report-");
        return executor;
    }
}
~~~

The code above is a **technical example illustrating snapshot passing**, not a complete reporting/security system. Spring manages the lifecycle and initializes the ThreadPoolTaskExecutor bean when configured via the container.

Points worth noting:

1. The controller obtains **userId** from **Principal**, rather than trusting a client-supplied userId.
2. The controller normalizes title and creates **ReportJobInput** containing **immutable Strings**, instead of passing HttpServletRequest, Principal objects, or request-scoped beans to the worker.
3. **@Async("reportExecutor")** specifies which executor the service uses. build is invoked by **another controller bean** through the Spring proxy; plain self-invocation within the same bean does not trigger the @Async interceptor.
4. The controller returns **CompletableFuture** so MVC can bind async processing to the result. This is not a **durable background job**; the result and request lifecycle remain tied to the HTTP response.
5. When business logic requires authorization at execution time, **a snapshotted userId does not replace authorization checks**. The worker must apply appropriate permission checks before privileged actions; this example merely builds a result string.
6. If the executor is overloaded, task submission may **be rejected immediately at the worker.build call**. A proper snapshot does not guarantee the task is accepted. Callers must handle overload appropriately.

Never pass an **@RequestScope bean** or **HttpServletRequest** into a task to be read after the request ends. A scoped proxy may fail to resolve its target once the worker lacks request context; sessions, servlet requests, and request attributes do not live as long as executor tasks.

## 10. CompletableFuture: Snapshot Before supplyAsync, Do Not Wait Inside the Lambda

Another anti-pattern:

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> callExternalService(request.getOwner(),
                        request.getItems()),
                executor);
~~~

This is an **illustrative snippet**, assuming request, executor, and callExternalService exist. The lambda fetches **owner** and **items** when the worker actually runs; it **does not fetch them when creating the CompletableFuture**. If the caller modifies request or the request lifecycle ends, the task may receive unintended data.

The right approach is usually:

~~~java
String owner = request.getOwner();
List<String> items =
        List.copyOf(request.getItems());

JobSnapshot snapshot = new JobSnapshot(owner, items);

CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> callExternalService(
                        snapshot.owner(),
                        snapshot.items()),
                executor);
~~~

This is also an **illustrative snippet** using existing types and context variables. Crucially, **the snapshot is created before** calling supplyAsync. **JobSnapshot** must be an appropriate immutable/defensive type, not just a DTO holding a mutable collection. **List.copyOf** still requires the source to be in a consistent state when copied.

With a CompletableFuture pipeline:

~~~java
CompletableFuture<Result> result =
        CompletableFuture.supplyAsync(
                () -> load(snapshot), executor)
            .thenApply(data -> transform(data, snapshot))
            .thenCompose(data -> saveAsync(data, snapshot));
~~~

This is **annotated Java pseudocode serving as an illustrative snippet**: you must declare Result, load, transform, saveAsync, and snapshot accordingly. The stages see the same captured snapshot. Do not assume non-async callbacks like **thenApply** always run on the request thread; non-async callbacks may run on the thread that completes the prior stage or the registering thread depending on completion state.

**Key point:** using CompletableFuture to build an async pipeline **does not automatically isolate mutable inputs**. Snapshots and object ownership remain the application's responsibility.

## 11. ThreadLocal, MDC, and SecurityContext Are Not Automatic Snapshots

Much web application context is bound to threads by the framework: **MDC logging**, **SecurityContext** in certain strategies, **RequestContextHolder**, and transaction context. When invoking an Executor, tasks may run on a different pool thread; that thread **does not automatically retain all caller ThreadLocals**.

Principles:

- **Business data:** pass explicitly via parameters or an immutable DTO.
- **Correlation/tracing:** use your observability/tracing framework's propagation mechanism or a properly designed **TaskDecorator** that cleans up context after the task finishes.
- **Security:** do not blindly copy the entire SecurityContext/Principal arbitrarily. Where framework and policy allow, use wrappers like **DelegatingSecurityContextAsyncTaskExecutor**; ensure permissions are verified at the right execution moment.
- **Transactions:** the submitting thread's transaction/persistence context **does not automatically transfer** to the worker. Establish a transaction boundary on the worker if transactional data access is needed.
- **Request context:** never assume HttpServletRequest, request-scoped beans, request attributes, or MultipartFile remain usable after the response has been returned.
- **Custom ThreadLocals:** if unavoidable, strictly manage **set/restore/remove in finally**. Thread pools reuse workers, so forgetting cleanup can leak data to subsequent tasks.

Also distinguish **context propagation** from **input snapshots**: propagation can restore technical context appropriate for a task, yet does not ensure mutable DTOs were properly snapshotted or security claims remain valid when the worker runs.

## 12. Spring Data/JPA: Prefer IDs and Frozen Data, Do Not Push EntityManager Across Threads

A common mistake is loading an entity inside an HTTP transaction and passing the raw entity to a worker for later processing.

Risks include:

- **EntityManager** and transaction-scoped persistence contexts are not designed for arbitrary cross-thread sharing.
- Entities may have **lazy associations**; worker access after the transaction/session closes can fail to load data.
- Mutable entities may still be modified by the caller or other layers, failing to provide a consistent snapshot.
- Database state may change between submission time and worker execution time.

Two strategies to distinguish:

**A. The task must use the latest state at execution time.** Capture only the **ID** and minimal business input, then let the worker open its own transaction and reload the entity with appropriate version/authorization checks.

~~~java
public record UpdateJob(long orderId, String actorId) {
}
~~~

**B. The task must process the exact content approved by the user at submission time.** Capture an **immutable DTO containing the approved data**, along with a **version**, or write a snapshot to durable storage inside the transaction/outbox if needed. Sending only orderId and loading "the latest version" would not satisfy this requirement.

In workflows with side effects where tasks must not be lost, **an internal executor is not a durable queue**. If the submitting transaction fails or the application restarts, an in-RAM Runnable can be lost. Consider a **transactional outbox**, durable queue, or job store, paired with idempotency and appropriate retry mechanisms.

## 13. Large Request Bodies, Files, and Streams: Do Not Copy Everything Into RAM

An appropriate snapshot must also respect a **resource budget**:

~~~text
10,000 pending jobs
  x 2 MB payload copied per job
  = roughly 20,000 MB of payload data excluding overhead
~~~

This is an **illustrative calculation**, not a metric gathered from a live system. Copying entire byte[]/multipart inputs into every task can sharply raise memory usage and GC pressure.

For files:

1. Validate size, format, and permissions **at the request boundary**.
2. If the worker runs after the request ends, **do not rely on temporary MultipartFile/request InputStream resources** staying alive.
3. Where appropriate, move the file to storage with a clear lifecycle, record **objectKey, checksum, size, version** in the snapshot, and have the worker fetch only what it needs.
4. Protect storage keys with access control, and never log sensitive content or expose it in public URLs.
5. Define cleanup if the task fails/cancels, if the job is rejected, or once it completes.

For secrets such as tokens/passwords, snapshot only what the worker is actually authorized and required to use. Prefer **references to a secret manager**, short-lived scoped access, task-specific tokens, or re-issuance based on permissions, rather than placing entire request headers/cookies and access tokens into long-lived queues.

## 14. Cancellation, Timeouts, and Overload Do Not Guarantee the Data Is Used

Even with an accurate snapshot, a task may **never execute**:

- The executor may reject the task due to overload or shutdown.
- The Future may be cancelled; the task may be interrupted or keep running depending on implementation and I/O state.
- The worker may fail before using the snapshot.
- An application deadline may expire before the task starts.
- The executor queue may build a backlog, making the snapshot stale relative to business reality.

Therefore, separate these questions:

| Question | Related mechanism |
| --- | --- |
| Is the passed data independent and from the right moment? | Snapshot / immutability / ownership |
| Was the task accepted by the executor? | Submit outcome, TaskRejectedException, metrics |
| Did the task actually complete? | Future/CompletableFuture, job state |
| Did the task complete within deadline? | Timeout / cancellation / queue wait |
| Does the task survive application restarts? | Durable queue / job store / outbox |
| Is the task authorized to read/write resources? | Authorization at the appropriate time |

**A correct snapshot does not solve delivery semantics.** A user sending a request receives HTTP 202 Accepted only when the application has genuinely **accepted the work per contract**; a failed submit or silently dropped Runnable is not business success.

## 15. When Snapshots Go "Stale": Timing and Business Contracts

"Capture before crossing threads" does not mean that data stays **valid forever**. For example:

- **Valid as of submit time:** a confirmation email must contain the product list and prices confirmed when ordering. A versioned/committed snapshot preserves exact historical content.
- **Valid as of execution time:** locking an account or processing a payment may require re-checking current state and permissions right when the task runs.
- **Needing both kinds of data:** the worker receives an immutable command representing user intent, yet reloads current state to validate preconditions.
- **With retries:** each retry should clarify whether to keep the original snapshot or refresh data; silent changes across retries can diverge from the original request.

In a sound design, **a snapshot represents a contract**: who creates it, when it is created, which fields are fixed values, which fields must be refreshed, and who is responsible for validation/recording.

If an application has multiple asynchronous stages, you do not have to reuse one giant object carrying all data end to end. Use **stage-specific immutable DTOs**, tailored to what each stage needs, reducing the risk of leaking data to components that do not need it.

## 16. Good Tests: Intentionally Mutate Source Data After Submit

To verify the system truly isolates inputs from tasks, test in a **coordinated sequence**:

1. Create mutable input with value **A**.
2. Create the snapshot properly before submit.
3. Submit to the worker while holding the worker with a **CountDownLatch**.
4. Mutate the source data to **B**, including any potentially shared nested collections/elements.
5. Open the latch so the worker reads the snapshot.
6. Assert the worker sees **A**, while the caller sees source **B**.
7. Use **Future.get(timeout)** to prevent hanging tests; release latches and shut down executors in finally.

The examples in sections 3, 4, and 5 tested respectively the **captured reference** bug, the fix using **List.copyOf with immutable elements**, and the **shallow copy with mutable elements** bug.

**Concurrency tests must never rely solely on Thread.sleep.** If the worker happens to run before the caller mutates, the test passes despite broken design. Latches/barriers pin down exact interleavings. Also test **copying while another writer mutates the data**; without ownership or locking, a copy API alone does not guarantee consistency.

For Spring applications, additionally test:

- Invoking **@Async** through the **Spring-managed proxy**, not merely calling new Service() directly.
- Ensuring workers do not touch stale **request scopes/transactions** after a request finishes.
- For large payloads, measuring queue and snapshot memory footprint.
- When submit throws **TaskRejectedException**, confirming the work is not reported as accepted.
- When tasks fail/cancel, confirming resources referenced in snapshots are cleaned up.

## 17. Common Conceptual Mistakes

**"Lambdas capture effectively final variables, so the data is immutable."** False. Effectively final only governs reassigning the local variable; the referenced object can still be mutated.

**"Records make all deeply nested fields immutable."** False. Records only fix component references; nested collections and objects remain mutable unless copied/defended.

**"List.copyOf on a List<MutableDTO> guarantees all data is frozen."** False. It does not clone the elements.

**"Collections.unmodifiableList(source) is a snapshot."** Not necessarily. An unmodifiable view can continue reflecting changes made to the source list.

**"Calling submit first guarantees the worker reads data before the caller modifies it."** False. The executor can delay running the task; even if concurrent, lacking ownership/synchronization is hazardous.

**"ExecutorService has happens-before, so immutable snapshots aren't needed."** False. Happens-before provides visibility for properly ordered actions, not isolation from writes occurring after submit.

**"@Async automatically carries HttpServletRequest, transactions, and all ThreadLocals to the worker."** Not guaranteed. Those contexts have separate scopes and propagation mechanisms.

**"Passing JPA entities through an executor is fine if read-only."** You cannot conclude that; lazy-loading proxies, persistence contexts, and mutable/transaction boundaries can still misbehave.

**"Snapshot the whole request to be sure nothing is missing."** Bad practice: requests contain too much data, potentially including tokens, streams, short-lived objects, and large payloads.

**"Copying byte[] once makes it immutable forever."** If the internal byte[] is returned or mutated by a worker, data still changes. Defensive copies on input/output or strict ownership contracts are needed.

**"One snapshot is always right for every retry."** Not necessarily. Tasks may need the submit-time version or the latest state; business rules must define which.

**"Submitting a Runnable means the job is durable."** False. An in-RAM executor does not replace a persistently backed job queue.

## 18. Applied Exercises

**Exercise 1.** A controller creates `List<String> filters`, then calls `executor.execute(() -> search(filters))`. Afterward, the controller adds an element to filters. Can filters be considered captured?

**Answer:** No. The lambda holds the same List reference. If the worker needs the contents at submit time, create **List.copyOf(filters)** before execute (and ensure no other thread is mutating filters while copying).

**Exercise 2.** Code uses `final MutableOrder order` and passes order to @Async. Is the final keyword sufficient?

**Answer:** No. It only prevents reassigning the order reference within the declaration scope; MutableOrder's setters and nested collections can still be modified.

**Exercise 3.** Using `List.copyOf(lines)` where each Line has a mutable price field. Can the worker see the new price after the caller changes it?

**Answer:** Yes, possibly. The new List holds the same Line instances. Convert each Line into an immutable snapshot of the values the worker needs.

**Exercise 4.** A worker sending an email one hour later needs the recipient's name and address as they were when the order was placed. Is sending only customerId and querying current data right?

**Answer:** Not reliably. If the customer updates their details during that hour, the output will differ. Use a versioned/committed snapshot of the confirmed data or a historical record to preserve semantics.

**Exercise 5.** A worker only needs orderId to load the latest order status and decide an action. Must you copy the entire order DTO?

**Answer:** No. Pass only the ID and minimal command metadata, then reload the data inside the worker's transaction with appropriate version/authorization checks.

**Exercise 6.** Why is copying via `new ArrayList<>(sharedList)` not guaranteed to be consistent?

**Answer:** If another thread concurrently mutates sharedList without synchronization, the copy process can observe an inconsistent state. Ownership, locks, or immutable publication is needed.

**Exercise 7.** A snapshot holds List.copyOf(strings), and a String variable in the source is reassigned. Will the worker see the new String?

**Answer:** Not through the created List snapshot: Strings are immutable and the copied List retains the elements present at creation time. Reassigning the source variable does not alter the String held in the snapshot.

**Exercise 8.** Why not pass HttpServletRequest or EntityManager directly into a CompletableFuture that runs after the HTTP response?

**Answer:** They have their own scopes/lifecycles and are not designed for arbitrary access on a worker after the request/transaction ends. Capture needed DTOs/IDs and re-establish resource boundaries on the worker.

**Exercise 9.** Input was snapshotted properly, yet the executor rejects the task. Can you return "processed"?

**Answer:** No. Capturing inputs properly only guarantees data suitability **if the task executes**. Acceptance status, errors, retries, and delivery semantics must be handled separately.

## 19. Checklist Before Handing Off a Task to Another Thread

- [ ] Identify precisely **which fields the task needs**.
- [ ] Read data **while the source still has a clear owner and valid scope**.
- [ ] Validate/normalize inputs and build the snapshot **before submit**.
- [ ] Ensure **immutability** at every necessary layer; defend against nested mutable objects.
- [ ] Do not copy a concurrently modified collection without synchronization.
- [ ] Do not arbitrarily pass short-lived requests, sessions, EntityManagers, or streams into tasks.
- [ ] Do not copy excess secrets, tokens, or personal data.
- [ ] Bound snapshot sizes and pending task counts.
- [ ] Decide whether data is **fixed at submit time** or **must be reloaded at execution time**.
- [ ] Have a contract handling **rejection, timeout, cancellation, retry, and shutdown**.
- [ ] Test with latches to verify mutating source after submit **does not change task data**.
- [ ] Attach observability/tracing using safe propagation mechanisms when needed, without mistaking propagation for a snapshot.

## Conclusion

**"Capturing appropriate input data before handing off to another thread"** means defining **timing**, **ownership**, **immutability level**, and **lifecycle** for the values a worker needs. With Java ExecutorService, CompletableFuture, and Spring @Async, lambdas and proxies **do not automatically clone mutable inputs**. A solid default approach is **normalizing and validating data on the request thread, building a minimal immutable DTO/record with defensive copies, and passing the snapshot as an argument to the worker**. When data is large, changes per business rules, or must be durable, use IDs/versions, proper storage, and separate transaction boundaries.

A proper snapshot prevents more than race conditions: it avoids leaking request contexts, reduces post-request/post-transaction failures, enables deterministic testing, and clarifies the contract between the submitting thread and the processing thread.

**Technical references:** Java SE 17 APIs for **ExecutorService**, **Future**, **List.copyOf**, **Arrays.copyOf**, and **CountDownLatch**; Spring Framework reference on **Task Execution and Scheduling**, **@Async**, request scopes, and Spring MVC asynchronous requests; Java Memory Model guidelines.
