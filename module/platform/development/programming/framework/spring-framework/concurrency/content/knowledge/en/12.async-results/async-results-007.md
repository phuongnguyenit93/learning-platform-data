# Returning Data Independent of Closed Resources

## 1. The Problem: A Completed Future Does Not Mean Resources Are Still Open

In Spring Framework, a task running via `@Async`, `AsyncTaskExecutor`, or `CompletableFuture` may read from a database, file, HTTP response, or stream and then return a result to the caller. A common mistake is **returning an object that still depends on an open resource**: a `ResultSet`, `InputStream`, JPA entity containing lazy associations, or a `Stream` reading data on demand.

For example: a task reads from the database inside a transaction, returns an entity, and ends the transaction; the caller then calls `entity.getItems()`. If `items` has not been initialized and the persistence context is no longer available, the operation can throw `LazyInitializationException`. Similarly, a `BufferedReader` returned after `try-with-resources` has closed the reader can no longer be read from.

**Principle:** at the moment an asynchronous result completes, the returned data must have **ownership and a lifecycle independent** of the resources the task closed, unless the API intentionally transfers resource ownership and explicitly defines who must close it.

Invariant to achieve for ordinary results:

```text
worker opens resource
      |
      v
reads all required values
      |
      v
converts into independently owned data (DTO / value object / immutable copy)
      |
      v
closes resource in finally / try-with-resources
      |
      v
Future completes with DTO
      |
      v
caller uses DTO: never accesses closed resource again
```

The keyword is **lifecycle independence**; not every piece of data has to be a `String` or `record`. A DTO can contain lists, maps, timestamps, and nested objects, as long as it does not secretly hold a JDBC cursor, uninitialized JPA proxy, session, stream, or mutable object being modified by another task.

## 2. Distinguishing Plain Data from Resource-Bound Handles

| What you want to return via Future | Lifecycle-dependent after worker leaves scope? | Appropriate handling |
| --- | --- | --- |
| `String`, `long`, `BigDecimal`, `Instant` | Normally no | Return directly once the value is computed |
| `record ReportDto(...)` holding only independent values | No, if fields are also independent | Return DTO; copy mutable collections/arrays when needed |
| Materialized `List<ReportDto>` | Not DB-dependent if elements are independent DTOs | Can use `List.copyOf` to keep structure immutable |
| JPA entity with `LAZY` relationships | May require persistence context when accessing unloaded fields | Fetch and map to DTO inside the transaction |
| Hibernate proxy / `PersistentCollection` | May require session or be affected by detachment | Do not return as a completed data result |
| `java.sql.ResultSet` / `Statement` | Depends on open statement/connection | Iterate `ResultSet` and map to values before closing |
| File/DB-backed `InputStream`, `Reader`, `Stream<T>` | Depends on open source and read ordering | Bounded materialization or streaming design with explicit resource ownership |
| Newly copied independent `byte[]` | Independent of original stream, yet mutable | Consider defensive copy, size, and mutation rights |
| `Path` or file ID in object storage | Is a locator, not an open handle | Can return locator; consumer must open a fresh source and handle file changes/deletion |
| `InputStreamResource` wrapping an open stream | Potentially single-use, depends on live stream | Do not return and then close the stream before framework reads it |

**Do not equate "the object still exists on the heap" with "the object is still usable."** Java's garbage collector keeps referenced objects alive, yet does not extend the transaction, database cursor, file descriptor, or HTTP connection that the object relies on.

A detached JPA entity **does not always fail**: simple attributes and already-loaded associations may still be readable. The issue is that the API implicitly depends on which attributes were fetched, which session remained open, and when the user invokes getters. An explicit DTO eliminates that fragile dependency.

## 3. Time and Thread Boundaries in Spring Concurrency

Suppose a controller calls an async bean and receives `CompletableFuture<ReportDto>`:

```text
HTTP/caller thread                        reportExecutor thread
------------------                        ---------------------
request -> async proxy
           |
           +-- submit task ---------------> @Async method begins
           |                                      |
           |                                open dedicated transaction
           |                                      |
           |                                JPA query, fetch required fields
           |                                      |
           |                                map ReportEntity -> ReportDto
           |                                      |
           |                                transaction ends
           |                                      |
           |                             Future completes with ReportDto
           |
caller gets handle  <------------------ result ready for get/join
           |
         get() / compose
           |
      use independent ReportDto
```

**Important point:** Spring imperative transactions using `PlatformTransactionManager` are normally bound to the current thread. The HTTP caller's transaction **does not automatically propagate** to the worker thread just because `@Async` returns a Future. Thus, querying and mapping must sit inside a transactional boundary **actually running on the worker** (via a call covered by Spring transactional advice).

JDK's `Future.get()` provides a *happens-before* relationship allowing the caller to observe writes made before task completion, but **does not reopen transactions or revive closed resources**. Never use memory visibility to solve lifetime bugs.

There are two independent boundaries to resolve:

1. **Concurrency boundary**: multiple threads may access the same object → requires an immutable snapshot or appropriate synchronization.
2. **Resource boundary**: in which scope resources are opened, who closes them, who retains usage rights → requires full materialization or explicit ownership transfer.

## 4. Wrong Example: Returning a JPA Entity and Accessing Lazy Relationships Later

The following is **illustrative code in a Spring Data JPA application**, not standalone Java:

```java
@Service
public class BadAsyncReportService {
    private final ReportRepository repository;

    public BadAsyncReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @Async("reportExecutor")
    public CompletableFuture<ReportEntity> loadAsync(long id) {
        // Suppose repository returns an entity with a LAZY collection.
        ReportEntity report = repository.findById(id).orElseThrow();
        return CompletableFuture.completedFuture(report);
    }
}
```

Caller:

```java
ReportEntity entity = reports.loadAsync(7L).get();
int count = entity.getItems().size(); // May fail if collection was not loaded.
```

Here `findById` may run under a repository-applied transactional boundary; once that boundary ends, unloaded LAZY associations can generally no longer be accessed safely. Some systems enable Open Session in View or have other session configs causing the bug **not to appear temporarily**; that is not a sound contract for async results. In particular, the request thread's persistence context does not become the worker's persistence context either.

Another mistake is returning `Stream<ReportEntity>` from a repository after the query transaction has closed. The Stream may need an open cursor/connection when the caller iterates it. Returning a reference to an unconsumed Stream **is not the same** as returning a completed list of data.

## 5. Right Pattern: Transactional Reader Builds a DTO Before Leaving Scope

Instead of letting an entity escape persistence management scope, convert all needed data into an independent DTO **before the transaction ends**.

Assuming the domain has `ReportEntity`, `ReportItem`, and `ReportRepository`; the snippets below are **illustrative Spring integration classes** placed in appropriate Java files with imports, not a standalone pure-JDK runnable program.

```java
public record ReportDto(
        long id,
        String ownerName,
        java.util.List<String> itemNames) {

    public ReportDto {
        itemNames = java.util.List.copyOf(itemNames);
    }
}
```

```java
@Service
public class ReportSnapshotReader {
    private final ReportRepository repository;

    public ReportSnapshotReader(ReportRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public ReportDto loadSnapshot(long id) {
        ReportEntity entity = repository.findById(id).orElseThrow();

        // Getters that may trigger LAZY fetches: execute inside
        // the transactional boundary on the reading thread.
        String owner = entity.getOwner().getName();
        java.util.List<String> names = entity.getItems().stream()
                .map(ReportItem::getName)
                .toList();

        return new ReportDto(entity.getId(), owner, names);
    }
}
```

```java
@Service
public class AsyncReportService {
    private final ReportSnapshotReader reader;

    public AsyncReportService(ReportSnapshotReader reader) {
        this.reader = reader;
    }

    @Async("reportExecutor")
    public CompletableFuture<ReportDto> loadAsync(long id) {
        // Runs on worker; calls reader bean through Spring proxy.
        ReportDto value = reader.loadSnapshot(id);
        return CompletableFuture.completedFuture(value);
    }
}
```

Requirements for the pattern to work properly:

- `@EnableAsync`, executor bean `reportExecutor`, Spring Data JPA, and transaction management are properly configured.
- `ReportSnapshotReader` and `AsyncReportService` **are two distinct Spring-managed beans**, constructor-injected. Thus, calling `reader.loadSnapshot(id)` from the worker can go through the `@Transactional` proxy. Avoid `this.loadSnapshot(id)` inside the same bean in proxy mode because self-invocation can bypass advice.
- Needed lazy associations are accessed/mapped while the transaction is still active. If the relationship graph has multiple levels, choose an appropriate fetch plan, entity graph, projection, or DTO query to avoid N+1 queries and over-fetching.
- The DTO holds a `long`, a `String`, and an immutable-copy `String` list; it carries no `EntityManager`, `Session`, or entity proxy outside the transaction.
- `CompletableFuture.completedFuture(value)` is created **inside the worker** after the reader finishes computing. The Spring async proxy returns the handle to the caller; it does not mean the caller is forced to run the method synchronously.

`@Transactional(readOnly = true)` is a transaction policy/read-only hint; it **does not turn an entity into an immutable DTO**, nor does it replace mapping. If careless mapping copies a `List<ReportEntity>` into the DTO, the result can still retain session dependencies and mutable state.

## 6. Standalone Java 17+ Example: Results Outlive the Reader

To prove this without needing a real database, the example below uses a `BufferedReader` closed by `try-with-resources` and an `ExecutorService` returning `Future`. The good case **reads all data and returns an independent record**; the bad case **returns a reader already closed inside the worker**.

Create file `DetachedDataDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class DetachedDataDemo {

    public record Snapshot(long id, String title, List<String> lines) {
        public Snapshot {
            lines = List.copyOf(lines); // Structurally immutable copy.
        }
    }

    static Snapshot readSnapshot() throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader("alpha\nbeta\n"))) {
            List<String> rows = new ArrayList<>();
            String line;
            while ((line = reader.readLine()) != null) {
                rows.add(line);
            }
            return new Snapshot(7L, "Q4", rows);
        } // reader is closed; Snapshot remains usable.
    }

    static BufferedReader brokenReader() throws IOException {
        BufferedReader reader =
                new BufferedReader(new StringReader("unread"));
        try (reader) {
            return reader; // Wrong: Java closes reader before returning result.
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Snapshot> good = pool.submit(DetachedDataDemo::readSnapshot);
            Snapshot value = good.get(); // Worker finished and reader is closed.
            System.out.println("snapshot = " + value.id() + "/" + value.title());
            System.out.println("lines = " + String.join(",", value.lines()));

            try {
                value.lines().add("gamma");
                System.out.println("immutable = false");
            } catch (UnsupportedOperationException ex) {
                System.out.println("immutable = true");
            }

            Future<BufferedReader> bad =
                    pool.submit(DetachedDataDemo::brokenReader);
            try {
                bad.get().readLine();
                System.out.println("closed reader fails = false");
            } catch (IOException ex) {
                System.out.println("closed reader fails = true");
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Run with JDK 17 or higher:

```bash
javac DetachedDataDemo.java
java DetachedDataDemo
```

Deterministic stdout:

```text
snapshot = 7/Q4
lines = alpha,beta
immutable = true
closed reader fails = true
```

**Explanation:**

1. `readSnapshot()` opens the reader inside the worker, iterates all lines into an `ArrayList<String>`, constructs `Snapshot` with `List.copyOf`, and closes the reader automatically upon exiting `try`.
2. The caller receives `Snapshot` via `Future.get()`. At this point the reader is no longer needed: data lives in `String` values and an independent list structure.
3. `List.copyOf` prevents structural mutations on the returned list; for example `add` throws `UnsupportedOperationException`. Because the elements are immutable `String`s, the snapshot here holds no references to external mutable data.
4. `brokenReader()` returns a reference to a reader inside `try-with-resources`, yet Java closes it **before the caller receives the result**. After `bad.get()`, `readLine()` throws `IOException`.
5. `Future.get()` synchronizes computation completion, yet **does not keep the data source open**. That is what makes the two branches yield different outcomes.

In the example, `StringReader` merely simulates a stream's lifecycle; real code could be `Files.newBufferedReader`, an `InputStream` from HTTP, or a JDBC cursor. The ownership rules remain identical. In production, shut down executors according to the application/bean lifecycle, rather than stopping a shared pool after every request.

## 7. A Similar Mistake with JDBC ResultSet

`java.sql.ResultSet` depends on `Statement` and `Connection`. The following snippet is **flawed by design**:

```java
public ResultSet loadRows(DataSource ds) throws SQLException {
    try (Connection connection = ds.getConnection();
         PreparedStatement statement =
                 connection.prepareStatement("SELECT id, name FROM report")) {
        return statement.executeQuery(); // ResultSet depends on statement.
    } // Statement and Connection are closed.
}
```

This is a **Java JDBC fragment**, requiring imports for `javax.sql.DataSource` and `java.sql` classes; not a standalone program. Returning `ResultSet` does not transfer connection ownership to the caller: `try-with-resources` closes the resources immediately upon exiting scope.

The right way is to build the result data right inside the scope:

```java
public List<ReportRow> loadRows(DataSource ds) throws SQLException {
    List<ReportRow> rows = new ArrayList<>();

    try (Connection connection = ds.getConnection();
         PreparedStatement statement =
                 connection.prepareStatement("SELECT id, name FROM report");
         ResultSet rs = statement.executeQuery()) {

        while (rs.next()) {
            rows.add(new ReportRow(rs.getLong("id"), rs.getString("name")));
        }
    }
    return List.copyOf(rows);
}

public record ReportRow(long id, String name) {}
```

This is an **illustrative fragment**, requiring `ArrayList`, `List`, JDBC imports, and declarations inside a valid Java structure. By the time the code returns, the connection, statement, and result set are closed; only a list of `long` and `String` values remains. Avoid forgetting to close `ResultSet` in direct JDBC code even though the statement normally manages it.

When a table has millions of rows, **do not materialize without bounds**. Consider pagination, chunking, managed file writing, or streaming data inside a properly scoped open resource with backpressure.

## 8. Why Is Stream<T> Especially Misleading?

`Stream<T>` in Java describes a *potentially lazy pipeline*, not a fully materialized collection. A stream from a plain `List<String>` may need no I/O, whereas a stream from a JPA repository, JDBC, file, or HTTP body may rely on an open connection/cursor/reader.

```java
// Illustrative fragment: DO NOT return a DB stream outside transactional scope.
@Transactional(readOnly = true)
public Stream<ReportEntity> streamReports() {
    return repository.streamAllReports();
}
```

If the caller calls `stream.forEach(...)` after the transaction ends, the resource may no longer be usable. Even if the stream still operates, consumers must know who is obligated to call `close()`, when the transaction ends, and whether accessing the stream from another thread is allowed.

Two safer models:

- **Bounded materialization:** open the source, iterate, map to DTOs, and collect into `List<DTO>` **before the transaction ends**; close the stream if required by the API.
- **Controlled true streaming:** the entire cycle of open source → read chunks → write to destination → close source happens inside a callback/function with clear ownership, rather than returning an open stream to the caller to read later.

Do not think `stream.toList()` solves everything on its own: it only solves **laziness and materialization** if called while the source is still open; collected elements could still be session-dependent entities/proxies. Elements must be mapped to independent data before placing them into the returned list.

## 9. Returning Results via CompletableFuture: Values Must Be Ready Before Completion

If manually using JDK `CompletableFuture.supplyAsync`, construct the value **inside the task** before returning:

```java
CompletableFuture<ReportDto> future =
        CompletableFuture.supplyAsync(
                () -> reportReader.loadSnapshot(reportId),
                executor
        );
```

This is an **integration code fragment** assuming `reportReader` is an injected bean, `reportId` is an ID, and `executor` is an existing `java.util.concurrent.Executor`. If `loadSnapshot` has Spring transaction management via proxy, calling it inside the lambda opens the boundary on the worker. If querying JDBC directly instead of calling a reader bean, the lambda should own the resources and return the DTO after `try-with-resources` finishes.

Conversely, never create a Future from a resource that will be closed before further processing:

```java
InputStream input = openInput();
try (input) {
    return CompletableFuture.supplyAsync(() -> parse(input), executor);
}
// Wrong: input may be closed right when the caller method returns,
// while the worker has not even started parsing yet.
```

This is **illustrative code showing broken ownership**, not a standalone method; `openInput`, `parse`, and `executor` must be defined in a real application. Fix: have `openInput()` happen **inside** the supplier and close right inside the supplier after parsing, or read sufficiently small data into an independent snapshot **before** submitting.

`CompletableFuture.completedFuture(value)` does not detach `value` automatically: if `value` is an entity containing lazy proxies or a closed stream, the Future still completes with that exact unsafe object.

## 10. Transferring Resource Ownership: An Intentional Exception

Not every system should load all data into RAM and return a DTO. For large files or video, streaming makes sense, yet you must design **who opens, who reads, and who closes**.

Spring MVC `StreamingResponseBody` example (controller snippet, requiring imports, `exports` bean, and Spring Web MVC config):

```java
@GetMapping("/exports/{id}")
public ResponseEntity<StreamingResponseBody> download(@PathVariable long id) {
    StreamingResponseBody body = output -> {
        // Open source INSIDE the callback performing streaming.
        try (InputStream input = exports.open(id)) {
            input.transferTo(output);
        }
        // Do not close the framework's output here.
    };

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .body(body);
}
```

In Spring MVC, the response-body-writing callback may run after the controller method has returned and is typically handled through async infrastructure. Opening the source **inside the callback** ensures the stream is opened when reading is actually needed. Configure appropriate MVC async executors and timeouts, plus policies for client disconnects.

A common mistake is opening `InputStream` in the controller and closing it when the controller returns, while the callback only starts reading afterward. Likewise, do not let the callback directly use an `EntityManager` or transaction that existed on the HTTP caller thread: the callback must create its own appropriate resource/transaction boundary.

This is **streaming with explicit ownership**, distinct from returning a materialized DTO. Other patterns like returning an object-storage locator, pre-signed expiring URL, or ID of a durably stored result also decouple ownership, yet must handle versioning, TTL, and availability when the caller uses it.

## 11. Input Data Also Has a Lifecycle

The problem does not only happen with **return values**; input passed from a request to an async task can also depend on an already-ended scope.

Example that should not be assumed safe:

```java
// Illustrative fragment in an HTTP controller:
executor.execute(() -> parse(request.getInputStream()));
```

`request` and the request stream are managed by the servlet container according to the HTTP processing lifecycle; the task might only start after the response has completed. To process asynchronously, copy the needed data (with size bounds) before leaving the request scope, or persist the payload to a durable store and pass an **immutable ID** to the worker. Temporary `MultipartFile` instances and request-bound streams require the same rule.

Example of deliberately passing small data:

```java
byte[] payload = request.getInputStream().readAllBytes();
byte[] snapshot = payload.clone();
executor.execute(() -> process(snapshot));
```

This is an **integration fragment**, not advice to read unbounded uploads into RAM. In practice, enforce size limits and validate input beforehand, avoiding passing mutable arrays to multiple writers; you can replace `byte[]` with a value object/DTO. For large payloads, store to file/object storage or a queue and pass a reference with controlled lifecycle.

A similar mistake: passing an entity attached to the caller's persistence context to a worker expecting the worker to invoke lazy getters, or expecting `@Transactional` on the caller to transfer the transaction to the worker. With Spring imperative transactions, that is not a valid guarantee.

## 12. Immutability: List.copyOf Is Only the First Step

A DTO free of closed resources solves only half the problem. The other half is preventing mutable state from being modified concurrently after the Future returns a result.

`List.copyOf(source)` creates a **structurally unmodifiable** list, yet it is a *shallow copy*: if elements are `MutableReportLine` objects with mutable fields, another caller can still mutate an element and affect readers. Likewise, a Java `record` does not automatically deep-copy `List`, `Map`, arrays, or custom mutable objects.

Example requiring defensive copies for `byte[]`:

```java
public final class DocumentBytes {
    private final byte[] content;

    public DocumentBytes(byte[] content) {
        this.content = content.clone();
    }

    public byte[] content() {
        return content.clone();
    }
}
```

This is a **standalone class** (save as `DocumentBytes.java` if running separately), illustrating that both constructor input and accessor output must be copied if you do not want callers able to mutate the internal array. For very large files, repeated copying can be expensive: prefer partitioned ownership models, buffers with clear lifetimes, or locators to persisted files.

Full checklist to follow:

1. Select only the fields the caller genuinely needs.
2. Map into independent values while resources are still alive.
3. Copy collections/maps/arrays and mutable elements when safe sharing is required.
4. Close resources before or while completing the boundary, passing out only result data.
5. Bound result sizes to prevent OOM or large backlogs in the executor.

## 13. Large Results: Do Not Trade resource-closed Errors for OutOfMemoryError

A `List.copyOf` holding a few hundred items is very different from querying millions of rows or reading multi-GB files. If materialized without limits, one task can consume the heap, cause long GC pauses, and degrade throughput of the entire `ThreadPoolTaskExecutor`.

Strategies for large data:

| What needs to be done? | Suitable design | Required conditions |
| --- | --- | --- |
| Return a few hundred records | DTO/record with bounded list | Clear pagination/limits |
| Return a large downloadable report | Worker writes output to file/object storage, Future returns ID/URI | Lifecycle/TTL/version/ACL; never return closed stream |
| Send chunks over HTTP | Streaming response opens resource inside callback | Timeouts, client disconnect, executor, and backpressure |
| Process millions of rows in batch | Paging/chunking in short transaction scopes; write output incrementally | Checkpoints, retry/idempotency, memory bounds |
| Read file by cursor | An object managing cursor lifetime and close rights with explicit API | Caller takes close responsibility; do not confuse with completed DTO |

For durably stored results, the Future can return `ExportReady(fileId, size, checksum)` instead of `InputStream`. When the caller needs to read the file, a service opens a **fresh** stream from the locator. Resource independence does not automatically mean data always exists: files can be deleted or overwritten by newer versions; thus handle not-found, TTL, object versioning, access checks, and retries.

## 14. How Do Errors and Cancellation Affect Resource Closing?

A proper resource-ownership pattern must work even when **tasks fail**, **time out**, or get **cancelled**:

- **Success:** build full DTO, close resources, complete Future with value.
- **Exception:** `try-with-resources` closes resources; Future completes exceptionally. Caller retrieves root cause via `get()`/`ExecutionException.getCause()` or `CompletableFuture.handle/exceptionally`.
- **Caller `get(timeout)` expires:** this is only a timeout on **the wait**, the task may still be running and holding resources. Never assume resources are already closed.
- **`future.cancel(true)`:** Future attempts to request worker interruption if implementation supports it; does not guarantee a JDBC call or I/O operation stops immediately. Resources should be closed in `finally` when code actually exits scope.
- **`cancel(false)`:** Future may transition to cancelled state while a running task can still continue; never treat `isDone()` as proof all resources were released.
- **Task rejected at submission:** resources **should not be opened beforehand and abandoned** if submission fails. Best practice is opening resources inside the task after executor acceptance.

In the JDK, `Future.get()` establishes result synchronization; meanwhile `CompletableFuture.cancel(...)` by implementation contract does not use interruption to control execution. Therefore, never hinge resource closing solely on `isCancelled()`: rely on `try-with-resources`/`finally` and cooperative cancellation design.

Detailed note: `close()` itself can throw exceptions. If a task built the DTO yet closing the resource fails while exiting `try-with-resources`, the Future may **complete with an error** instead of returning the DTO, depending on exception handling. Avoid swallowing close errors if they matter to work integrity.

## 15. How to Test That Results Are Truly Independent

A good test needs to **read the data after the resource scope has closed** rather than asserting only while the transaction is open.

Suggested scenario for a `loadAsync(id)` service:

1. Create test data with LAZY associations and collections to read, and run the task through a real executor (not just calling the target method directly).
2. `Future.get()` waits for task completion. If using Spring JPA, verify the service has already exited the transactional method before evaluating the result.
3. On the caller **with no persistence context available for reading**, access every field of the DTO, iterate collections, and serialize to JSON. No additional queries or hidden new sessions may be needed.
4. Verify lists, maps, and arrays remain unchanged if the original objects or collections are modified afterward.
5. For JDBC/files, use test fakes with a `closed` flag or actually close the resource and confirm the caller can still read the DTO.
6. Exercise exception/cancellation/timeout branches; verify `close` runs properly and no connections/file descriptors leak.
7. Test near-limit sizes, multi-task concurrency, heap usage, and queue wait times to spot bad behavior under large materialization.

If the application has Open Session in View enabled, consider disabling it in boundary tests or actively asserting no queries/lazy-loading occur after the service created the DTO; otherwise, a request-scoped session can mask a lazy-loading bug. Never claim `@Transactional` on the test method alone is enough: the test transaction can make data appear valid while production scope would already be closed.

## 16. Common Design Mistakes

1. **Returning `ResultSet` out of `try-with-resources`.** Statement/connection are already closed; `ResultSet` no longer has a valid usage contract.
2. **Returning a JPA entity with LAZY associations through a Future.** Caller may access them after the session/transaction has ended.
3. **Creating a DTO whose fields are still entities or `PersistentCollection`s.** "Renaming the outer type" does not create an independent snapshot.
4. **Returning `Stream<T>` intending to iterate it in the caller.** The stream may require a connection/file that was not kept alive and properly closed.
5. **Thinking Future keeps the transaction alive until `get()`.** Future only holds a result/status handle; it does not manage transaction lifecycle.
6. **Using `@Transactional` on the HTTP caller and assuming the worker shares the transaction.** Imperative transactions are thread-bound by default; create proper boundaries inside the worker.
7. **Calling `this.readTransactional()` inside the same bean.** In default proxy mode this can bypass transactional advice; separate beans and call through the proxy.
8. **Directly serializing a JPA entity after the Future finishes.** The serializer may hit LAZY getters when the session is already closed.
9. **Opening `InputStream` in the caller and closing it before the worker/callback uses it.** Move open/close operations to the true owner's scope.
10. **Believing `List.copyOf` deep-copies every element.** It does not copy mutable internals inside elements.
11. **Loading every record into RAM to avoid lazy loading.** Can cause OOM; apply limits, pagination, chunking, or controlled streaming.
12. **Reading request body or `MultipartFile` on a worker after request scope ends.** Never assume servlet/container-managed resources stay open.
13. **Equating `cancel(true)` with closing connections immediately.** Cancellation is cooperative; `finally` and downstream timeout policies are needed.
14. **Returning a file path and assuming the file cannot change.** A locator is stream-independent, yet still requires permission, version, and lifetime management.
15. **Not testing after resources have closed.** Tests running purely inside a transaction often miss bugs appearing on a different caller thread.

## 17. Knowledge Self-Check

**Question 1.** An `@Async` task returns `Future<ReportEntity>`; caller's `get()` succeeds, yet `entity.getItems()` subsequently throws an error. Why?  
**Answer:** The Future completed, yet the LAZY association still depends on a persistence context/session that is no longer usable. Required data must be mapped into a DTO inside the worker's transactional scope.

**Question 2.** If `ResultSet` is returned from a method inside `try(Connection c=...)`, should the caller continue calling `rs.next()`?  
**Answer:** No. `ResultSet` has a lifecycle dependent on Statement/Connection; read it completely or paginate inside scope and return independent values.

**Question 3.** Does `Future.get()` extend the lifetime of an `InputStream` that the task closed?  
**Answer:** No. It only waits/receives result status and establishes memory synchronization.

**Question 4.** Is `record ReportDto(List<MutableItem> items)` with `List.copyOf(items)` deeply immutable?  
**Answer:** No. The list cannot be structurally modified, yet individual `MutableItem` instances can still be mutated if references are shared.

**Question 5.** A 4 GB file needs to be served over HTTP. Should a 4 GB `byte[]` be returned from a Future?  
**Answer:** Usually no. Prefer returning a locator to durable storage or streaming with explicit open/close ownership and resource bounds.

**Question 6.** In Spring MVC streaming, should `InputStream` be opened before the controller returns or inside the `StreamingResponseBody` callback?  
**Answer:** Normally open it inside the callback that actually consumes the data, and close it when the callback finishes; do not assume a stream opened earlier stays alive.

**Question 7.** A task timed out on `get(timeout)`. Can we conclude the JDBC connection has already been closed?  
**Answer:** No. The worker may still be running; deadlines, cooperative cancellation policies, and `try-with-resources`/`finally` are required to release it at the right time.

**Conclusion:** let the asynchronous task **own and close** the resources it opens, and return **a completed, independent value safe to use on another thread**. If data is too large to materialize, switch to a design with **explicit ownership** for streaming or durably stored files; never sneak an expired cursor/stream/session through a `Future`.

### References

- [Spring Framework — Task Execution and Scheduling (@Async, Future)](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Declarative Transaction Management, thread-bound transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Data JPA — DTO and projection queries](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Spring Framework — StreamingResponseBody](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/StreamingResponseBody.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java SE 17 — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
