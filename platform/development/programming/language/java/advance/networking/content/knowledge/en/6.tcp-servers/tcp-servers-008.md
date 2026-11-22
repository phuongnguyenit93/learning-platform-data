# Synchronizing Shared Data Without Locking the Entire TCP Server Read/Write Path

A TCP server can serve many sockets simultaneously. Each thread handling a connection typically has to **read from the network, decode, validate the request, update shared state, and write the response**. If you wrap that entire cycle in a shared `synchronized` block, just **one slow client** can force every other client to wait on the lock, even when those clients are operating on independent data.

The right goal is: **synchronize at the boundaries where data genuinely requires consistency**, choose the appropriate thread-safe/atomic structure, and keep the network I/O path independent from the locks protecting data. "Not locking the entire read/write path" **does not mean never using locks at all**; sometimes a small, properly scoped lock is the simplest and safest choice.

This lesson is part of the **TCP Servers** topic, using Java 17+. After this lesson, you will be able to choose solutions for counters, sessions, rooms/subscriptions, quotas, or aggregated state; distinguish atomicity, visibility, and response-sending order; and design backpressure instead of creating unbounded queues.

## 1. Separating Per-Connection I/O from Shared Data

Separate what each client owns from what multiple clients access concurrently.

```text
                         TCP SERVER
     accept() -> Socket A ---> Handler A --\
     accept() -> Socket B ---> Handler B ----+--> Shared State
     accept() -> Socket C ---> Handler C --/       |
             |                     |               +-- counters
             |                     |               +-- sessions/rooms
             v                     v               +-- quota/metrics
       socket-specific        socket-specific
       reader/writer           parser/buffers
```

- **Per-connection data:** the accepted `Socket`, incomplete frame read buffers, parser state, per-connection request sequence numbers, and the client's dedicated output queue. If only one handler owns this data, no global lock is needed.
- **Data shared across connections:** the map of active users, processing counts, quotas, chat room state, shared cache, and subscription registry. When multiple threads access it concurrently, a synchronization policy is required.
- **Immutable data:** configuration/read-only snapshots, once safely published, can usually be read without locks; to change them, publish a new version using atomic/visibility mechanisms.

Key takeaway: `read()`, `readLine()`, `accept()`, and `write()` can **block on the network**, whereas map/counter updates should normally take only a tiny fraction of time in CPU/RAM. Do not combine both kinds of work into the same critical section across all clients.

## 2. Anti-Pattern Example: Holding a Global Lock While Waiting on a Socket

The following code is an **illustrative snippet, not a standalone program**; assume `serverLock`, `in`, `out`, and `sharedMap` are already defined:

```java
synchronized (serverLock) {
    String command = in.readLine();       // May wait indefinitely for data.
    updateSharedMap(sharedMap, command);  // Only this step needs synchronization.
    out.write("OK\n");                    // May wait on a slow-receiving peer.
    out.flush();
}
```

If client A connects but is slow to send a newline, handler A holds `serverLock` inside `readLine()`. Clients B, C, and D, even with commands already ready, cannot enter processing. If peer A reads the response slowly, the write operation can also block while still holding the lock. This is the risk of **head-of-line blocking caused by application lock design**; it is distinct from TCP's internal byte-ordering mechanism.

A sensible separation:

```text
Handler A:
  1. Read and assemble frame A  [without holding global data lock]
  2. Validate, parse            [local data]
  3. Small atomic update        [only the required data region]
  4. Build response             [local data]
  5. Send on socket A           [without holding global data lock]
```

**Do not perform network I/O, wait on `Future.get()`, `Thread.sleep()`, call remote APIs, or execute long blocking operations inside a shared data lock.** When business logic needs to wait on an external resource, separate that step out and redefine how invariants are maintained (for example, switching to a reservation/state machine with explicit states).

## 3. Three Properties of Thread Safety: Atomicity, Visibility, and Ordering

**Atomicity:** an operation is observed as an indivisible state transition within its promised scope. For example, `AtomicLong.incrementAndGet()` atomically updates a single number; `ConcurrentHashMap.merge(key, 1L, Long::sum)` atomically updates the value for **a single key**.

**Visibility:** changes made by one thread are visible to another thread according to the *happens-before* rules of the Java Memory Model. Proper synchronization can come from `volatile`, `synchronized`, `AtomicReference`, concurrency classes, or safe immutable publication. Using a plain `HashMap` and merely "hoping another thread sees it" is invalid.

**Ordering:** the order of shared-data mutations and the order of responses must be clearly defined. TCP preserves byte order **within each direction of each individual connection**, but it does not automatically order operations of handlers from different sockets. Two clients sending nearly at the same time have no default "global order."

For example, `volatile long count; count++;` is still unsafe for a counter: `volatile` provides visibility for each individual read/write, but `count++` is **read → add → write**, which can lose updates when multiple threads interleave.

```java
// Correct illustration for a shared counter (not a standalone class).
AtomicLong count = new AtomicLong();
long next = count.incrementAndGet(); // atomic read-modify-write
```

Atomicity of **a single variable** still does not mean two variables or multiple keys are updated in **a single atomic transaction**.

## 4. Choosing the Right Mechanism for the Invariant

| Shared Data Pattern | Typically Suitable Java 17+ Tool | Scope and Limitations |
| --- | --- | --- |
| A counter needing exact values on update | `AtomicLong.incrementAndGet()`, `compareAndSet` | Atomic for exactly one variable; does not group multiple fields |
| Hot statistical counter with many writer threads | `LongAdder.increment()` | Optimizes contention; `sum()` may not be an atomic snapshot during writes |
| Map with per-key operations | `ConcurrentHashMap.merge`, `compute`, `putIfAbsent` | Atomic per key/operation; does not create a transaction across multiple keys |
| A group of fields that must be read as a consistent version | Immutable record + `AtomicReference<State>` | Replaces entire state via CAS; update function must be pure and retry-safe |
| A few fields updated together with low contention | `synchronized`/`ReentrantLock` around a **short update block** | Lock only variables sharing an invariant; release lock before I/O |
| Single owner for an entity/room | Queue into an actor/owner task or partition by key | No mutable state shared across writers; requires a bounded queue and overload handling |
| State replaced only via new snapshots | `volatile` or `AtomicReference` pointing to an immutable object | Publish as-is; never mutate a map/list after publishing |

**No single primitive fits every problem.** `ReadWriteLock` can make sense for read-heavy, write-light in-RAM workloads, but if a read lock is held while writing to a socket, a slow client still stalls writers. `StampedLock` requires following validate/retry rules properly and is not a default upgrade for every TCP server.

## 5. Shared Counters and Maps: Eliminating Non-Atomic Read-Modify-Write

The following design has a **lost update** even though the map is a `ConcurrentHashMap`:

```java
// Incorrect illustration: get + put is not an atomic increment.
long previous = counters.getOrDefault("apple", 0L);
counters.put("apple", previous + 1);
```

Suppose A and B both read `previous=10`, each computes `11`, and both write `11`. The result should have been `12` but is only `11`. A `ConcurrentMap` protects its internal structure from races; **it does not automatically combine two API calls into one transaction**.

Replace it with an operation that is atomic per key:

```java
// Illustration with counters as ConcurrentHashMap<String, Long>.
counters.merge("apple", 1L, Long::sum);
```

`merge` performs a per-key atomic operation and applies the summing function to the existing value. The remapping function in `merge`/`compute` must be **fast, non-blocking, and side-effect-free**—do not call sockets, network logging, or recursively mutate the same map. Using `Long` risks overflow if values grow too large; real systems must choose appropriate types and overflow policies.

If you only need to measure metrics under load, you can use:

```java
// Illustration, same java.util.concurrent package.
ConcurrentHashMap<String, LongAdder> hits = new ConcurrentHashMap<>();
hits.computeIfAbsent("apple", ignored -> new LongAdder()).increment();
long currentEstimate = hits.get("apple").sum();
```

`LongAdder` reduces contention with many writers, but `sum()` **is not an atomic transaction with respect to concurrent updates**. Do not use this sum as a mechanism to enforce exact quotas or financial limits.

## 6. Java 17+ Program: Multiple TCP Clients Updating Shared State

**`ConcurrentTcpCounters.java`** creates a `ServerSocket` on loopback with an OS-assigned port, 4 clients, and 4 handlers. Each client sends 200 rounds consisting of two commands, `INC apple` and `INC orange`, then closes **its output direction** so the server knows the client's command stream has ended. Each handler reads and processes from its **own** socket, updates the shared map via `merge`, and returns `OK 400`. No `synchronized` block wraps the `readLine()` or `write()` loop across all clients.

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ConcurrentTcpCounters {
    private static final int CLIENTS = 4;
    private static final int ROUNDS = 200;

    private static void handle(
            Socket socket, ConcurrentHashMap<String, Long> counters)
            throws IOException {
        try (socket) {
            socket.setSoTimeout(10_000);
            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            socket.getInputStream(), StandardCharsets.UTF_8));
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            socket.getOutputStream(), StandardCharsets.UTF_8));

            int processed = 0;
            String line;
            while ((line = in.readLine()) != null) {
                String key;
                if (line.equals("INC apple")) {
                    key = "apple";
                } else if (line.equals("INC orange")) {
                    key = "orange";
                } else {
                    throw new IOException("Invalid command");
                }
                counters.merge(key, 1L, Long::sum);
                processed++;
            }

            // Only this handler writes to this client's output stream.
            out.write("OK " + processed);
            out.newLine();
            out.flush();
        }
    }

    private static String runClient(InetAddress address, int port)
            throws IOException {
        try (Socket socket = new Socket(address, port)) {
            socket.setSoTimeout(10_000);
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            socket.getOutputStream(), StandardCharsets.UTF_8));
            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            socket.getInputStream(), StandardCharsets.UTF_8));

            for (int i = 0; i < ROUNDS; i++) {
                out.write("INC apple");
                out.newLine();
                out.write("INC orange");
                out.newLine();
            }
            out.flush();
            socket.shutdownOutput();

            return in.readLine();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        ConcurrentHashMap<String, Long> counters =
                new ConcurrentHashMap<>();
        ExecutorService serverWorkers =
                Executors.newFixedThreadPool(CLIENTS);
        ExecutorService clientWorkers =
                Executors.newFixedThreadPool(CLIENTS);

        try (ServerSocket server = new ServerSocket(0, CLIENTS, loopback)) {
            server.setSoTimeout(10_000);
            int port = server.getLocalPort();

            List<Future<String>> clients = new ArrayList<>();
            for (int i = 0; i < CLIENTS; i++) {
                clients.add(clientWorkers.submit(
                        () -> runClient(loopback, port)));
            }

            List<Future<?>> handlers = new ArrayList<>();
            for (int i = 0; i < CLIENTS; i++) {
                Socket accepted = server.accept();
                handlers.add(serverWorkers.submit(() -> {
                    handle(accepted, counters);
                    return null;
                }));
            }

            boolean allAcknowledged = true;
            for (Future<String> response : clients) {
                allAcknowledged &=
                        ("OK " + (2 * ROUNDS)).equals(response.get());
            }
            for (Future<?> handler : handlers) {
                handler.get();
            }

            Map<String, Long> afterAllHandlers = Map.copyOf(counters);
            System.out.println("All responses OK: " + allAcknowledged);
            System.out.println(
                    "apple: " + afterAllHandlers.get("apple"));
            System.out.println(
                    "orange: " + afterAllHandlers.get("orange"));
        } finally {
            clientWorkers.shutdownNow();
            serverWorkers.shutdownNow();
        }
    }
}
```

Run on JDK 17+:

```sh
javac -encoding UTF-8 ConcurrentTcpCounters.java
java ConcurrentTcpCounters
```

Stdout on a successful run:

```text
All responses OK: true
apple: 800
orange: 800
```

Why is the result deterministic?

1. Each client sends `200 × 2 = 400` valid commands; each handler increments the counter **atomically per key**. Four clients produce a total of `800` increments for each key.
2. `Future.get()` on all handlers completes before `main` reads the final result. At that point no writers remain on the map, so `Map.copyOf(counters)` represents the exact state **after activity has quiesced**.
3. While handlers are still running, `Map.copyOf(counters)` or iterating over `ConcurrentHashMap` **does not create a simultaneous atomic snapshot across multiple keys**. Between an `apple` increment and an `orange` increment, the two values may temporarily diverge.
4. The client receives the **demo protocol** ACK after the server has called `merge` for all commands on that connection. This is not proof that data has been persisted to disk: the demo stores all counters **in RAM** and defines ACK only within RAM scope.

The code limits loopback, client count, and round count to keep the demo deterministic. In production, you must bound the number of active connections, line length, request count, lifetime, and handling when a client sends too fast or omits newlines. `BufferedReader.readLine()` **does not limit line length by itself**; if data comes from the Internet, a bounded parser is required.

Java 17 note: `ExecutorService` is not used in a try-with-resources block in this example; the program calls `shutdownNow()` in `finally` after awaiting futures. For long-running servers, design a more precise quiesce/shutdown; calling pool shutdown **does not automatically close every socket blocked in I/O**.

## 7. When Multiple Fields Must Be Consistent: Replace the Whole Immutable State

Suppose a server tracks two metrics, `accepted` and `rejected`, and a monitoring thread must observe both at **the same logical point in time**. Two separate `AtomicLong`s prevent lost updates for each field, but reading `accepted.get()` and then `rejected.get()` does not guarantee the two values belong to the same version.

You can publish an immutable record containing both fields using `AtomicReference<Metrics>`. Each update uses CAS to replace **the entire record**. A thread reading `metrics.get()` obtains a single consistent snapshot of both fields. Standalone example **`AtomicTcpMetrics.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public class AtomicTcpMetrics {
    private record Metrics(long accepted, long rejected) {}

    public static void main(String[] args) throws Exception {
        AtomicReference<Metrics> metrics =
                new AtomicReference<>(new Metrics(0, 0));
        ExecutorService workers = Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> jobs = new ArrayList<>();
            for (int worker = 0; worker < 4; worker++) {
                final boolean accept = worker % 2 == 0;
                jobs.add(workers.submit(() -> {
                    for (int i = 0; i < 1_000; i++) {
                        metrics.updateAndGet(old -> accept
                                ? new Metrics(
                                        old.accepted() + 1, old.rejected())
                                : new Metrics(
                                        old.accepted(), old.rejected() + 1));
                    }
                }));
            }
            for (Future<?> job : jobs) {
                job.get();
            }

            Metrics snapshot = metrics.get();
            System.out.println("Accepted: " + snapshot.accepted());
            System.out.println("Rejected: " + snapshot.rejected());
            System.out.println("Total: " +
                    (snapshot.accepted() + snapshot.rejected()));
        } finally {
            workers.shutdownNow();
        }
    }
}
```

Run:

```sh
javac -encoding UTF-8 AtomicTcpMetrics.java
java AtomicTcpMetrics
```

Deterministic output:

```text
Accepted: 2000
Rejected: 2000
Total: 4000
```

`updateAndGet(old -> new Metrics(...))` may invoke the lambda again if CAS fails because another writer just updated the reference. Therefore, the lambda must be **pure**: no writing to sockets, no incrementing external counters, no database calls, no sending messages. In the example, the only real side effect is the single successful publication of the new state.

**Trade-off:** each update allocates a new object, and CAS may retry frequently under high contention. This fits small state with tight invariants, versioned configuration, or management metadata; do not use it by default for millions of hot counters. When a transaction involves a DB, durable state, and exactly-once rules, an in-RAM atomic snapshot **cannot replace a data store transaction**.

## 8. Which Invariants Require a Short Lock or Data Redesign?

Suppose `maxConnections=100`, and a thread must enforce "admit a new client only if a slot is available." The following snippet has a race:

```java
// Incorrect when multiple handlers concurrently check and then increment.
if (active.get() < maxConnections) {
    active.incrementAndGet();
    admitClient();
}
```

Two threads can both observe 99 and both increment to 101. A CAS solution checks and increments **in the same loop**:

```java
// Method illustrating a standalone signature.
static boolean tryReserve(AtomicInteger active, int max) {
    while (true) {
        int count = active.get();
        if (count >= max) {
            return false;
        }
        if (active.compareAndSet(count, count + 1)) {
            return true;
        }
    }
}
```

Call `admitClient()` **only after** reservation succeeds. When handling finishes, release the slot **exactly once** in the corresponding `finally` block; if reservation failed, do not decrement. If the limit involves multiple conditions or related data pieces (user, room, global quota), you may need **a short lock protecting the entire invariant**, an actor owning the key, or a DB transaction—do not use separate atomic operations and assume the whole group is atomic.

Example of the short-lock pattern:

```java
// Illustration: only update in-RAM state under the lock.
Decision decision;
synchronized (stateLock) {
    decision = decideAndMutateSharedState(command);
}
// Only perform network I/O after releasing the lock.
sendResponse(socket, decision);
```

`decision` should be an immutable result for that request. If `sendResponse` fails, the updated state does not automatically roll back: business policy must define whether a failed response requires retry/idempotency or a compensating mechanism. If validation is slow or depends on I/O, do not hold the lock while waiting on it.

## 9. Same Socket: Synchronize the **Connection's Writer**, Not the Whole Server

Avoiding a global lock **does not mean multiple threads can write whatever they want to the same `OutputStream`**. When multiple asynchronous tasks send responses to the same client, bytes from two messages can interleave if write calls, headers, and payloads interleave in time. TCP only guarantees the order of **the byte sequence actually written**; it does not define message boundaries or keep frames intact for Java code.

For example, suppose two producers want to send two length-prefixed frames:

```text
Producer A: [length(A)] [payload(A)]
Producer B: [length(B)] [payload(B)]

If written concurrently to the same output:
[length(A)] [length(B)] [payload(A)] [payload(B)]
=> The peer parser may misinterpret length(B) as the start of payload(A).
```

The preferred solution is **a single writer owner per connection**:

```text
Request handler A --\
Request handler B ----> bounded outbound queue(socket-42) -> WRITER(socket-42)
Notification task ----/                                   -> Socket OutputStream
```

Producers build a **complete, immutable frame** and `offer` it to the queue; a single writer takes frames and sends them in queue arrival order. If using `ArrayBlockingQueue`/`BlockingQueue`, choose capacity, timeout, or full-queue policy. The queue guarantees **successful-enqueue** order, not "business order" between two concurrent producers; if ordering by request ID is required, enforce rules at the protocol layer.

In simple systems, a lock **dedicated to that socket** can wrap the writing of a complete frame to prevent interleaving, but writing to a socket can block when the peer is slow; never share that lock across all sockets. With multiple producers or high traffic, a bounded queue plus an owner writer usually isolates slow clients better and applies clearer backpressure.

## 10. Key-Based Synchronization, Actors, or Event Loops: Choose by Sharing Pattern

**Per-key atomic update:** Maps holding per-user/room counters, sessions, or objects. Changes affecting only one key can use `ConcurrentHashMap.compute` or atomic state inside the value. Compute callbacks must be short; avoid calling blocking operations or recursively modifying the same map from inside the callback.

**Single-writer / per-room actor:** All mutations for the same room go through one queue and one owner task, while other rooms make progress independently. The benefit is that room invariants are easy to reason about; the cost is that the queue must be bounded and a slow owner can build up a backlog for that room. If a TCP connection has not finished reading a frame, its dedicated handler must assemble/parse the full frame before sending the command to the actor.

**Sharding/partitioning:** Choose an owner via `hash(key)` or fixed partitions. Keys in the same shard have queued update ordering, while keys in different shards are processed in parallel. Operations spanning multiple shards require a coordination protocol or storage transaction; system-wide atomicity does not emerge automatically.

**NIO/event loop:** With `SocketChannel` and `Selector`, a single event loop can manage many connections, reducing blocking threads. Even so, **do not perform blocking external network I/O, heavy CPU work, or DB waits directly on the event-loop thread**. Shared state still needs ownership or synchronization when multiple event loops or workers exist. An event loop does not automatically solve data races across other threads.

A general rule: **route data to the right owner**, then perform a short update; do not place a long lock over the entire data path just because there are many sockets.

## 11. Backpressure and Resource Bounds Are Part of Concurrency Design

If handlers update very quickly while the writer sends responses to a slow client, the output queue will grow unbounded unless capped. Similarly, an `ExecutorService` with an unbounded task queue can retain too many frames, `byte[]` buffers, or client contexts, leading to heap/GC pressure and service outages.

Choose concrete bounds:

- **Connections:** concurrent socket/handler count, idle connection timeout, per-tenant/client limits.
- **Input:** frame size, incomplete byte count, commands per window, read/parse rate.
- **Shared state:** map size, session TTL/cleanup, key count, value limits.
- **Output:** per-connection bounded queue, full-queue policy (bounded wait, return error, drop permitted notifications, or close peer).
- **Worker pool:** bounded queue and rejection policy; do not ignore `RejectedExecutionException` or spawn unbounded threads to drain backlogs.

`BlockingQueue.put()` can block the sending thread when full; `offer()` can reject immediately, and `offer(timeout)` waits for a bounded duration. The choice depends on your SLA/protocol. **If losing required responses is not permitted**, do not arbitrarily choose dropping as an optimization; return an error, throttle, or close the connection in a controlled manner while keeping business state consistent.

Do not put `Socket.write` inside a `ConcurrentHashMap.compute` callback or hold a state `ReentrantLock` while waiting for a queue to drain. Doing so turns a slow peer's speed into a bottleneck for every request needing that state.

## 12. Publishing Snapshots and Observing Metrics with the Right Guarantees

A dashboard may accept *best-effort* metrics, whereas a quota controller needs consistent results:

| Question | Appropriate Read/Synchronization Approach |
| --- | --- |
| "How many commands did each key receive once updates stop?" | Read `ConcurrentHashMap` after `Future.get()`/quiescence |
| "Approximate requests/s while the system is running?" | `LongAdder`, sampling; accept mid-flight readings |
| "Can we admit another session without exceeding quota?" | Atomic CAS/lock/actor for **check + reserve** |
| "Must accepted and rejected belong to the same version?" | Immutable `State` + `AtomicReference.get()` |
| "Need an exact report across multiple keys while writers are active?" | Versioned overall state, quiesce, snapshot protocol, or transaction—do not expect `Map.copyOf` to freeze all writers |
| "Must business response wait until DB commit?" | DB transaction + protocol acknowledgement; concurrent memory only solves within one JVM |

Distinguish a **thread-safe collection** from a **thread-safe algorithm**. A `ConcurrentHashMap` makes `get` and `put` structurally safe, but the sequence "check capacity → increment counter → allocate resource → send response" needs an atomicity contract for **the entire decision**.

For read-mostly configuration, publishing a new immutable object via `volatile`/`AtomicReference` lets readers use an unchanging version without lock contention. Avoid returning references to a mutable `HashMap`/`ArrayList` and letting other threads mutate it after publication.

## 13. Connection Teardown, Task Cancellation, and Shared State Lifecycle

Shared data synchronization also involves deleting and releasing resources:

1. When a handler exits a connection, perform cleanup in `finally`, cancel subscriptions, release reserved quotas, and close the `Socket` **idempotently** if multiple error paths can trigger cleanup.
2. **`ExecutorService.shutdown()`** stops accepting new tasks; `awaitTermination` waits for a bounded time; when forcing a stop, `shutdownNow()` issues interrupts but **does not guarantee** waking every blocking socket read on a classic `Socket`. The owner must manage and close the corresponding socket to unblock I/O.
3. If owning an output queue, define how to close the queue, flush remaining frames, and handle a "poison pill"/shutdown state without getting stuck on a full queue. Do not wait indefinitely under a shared-state lock.
4. **Closing a connection after sending a response** does not prove the peer read or committed the response. If a request mutates durable data, design idempotency and explicit application acknowledgements.
5. Session maps risk stale entries when a handler crashes or times out; use a per-session identity/token so an old session's cleanup does not accidentally remove a new session for the same user. For example, `sessions.remove(userId, expectedSession)` removes the entry only if the value is still the expected object.

With any concurrency mechanism, explicitly state who is the **owner of the socket**, the owner of an entry in the shared map, and who is permitted to close/evict. Without clear ownership, cleanup races are often harder to diagnose than counter-increment races.

## 14. Testing Correctness Instead of Relying on Timing

A "run one client, looks OK" test does not prove a server is race-free. Tests need multiple clients and **final invariant checks**:

- Have multiple clients concurrently send commands to the same key; if each client sends `N` commands, the final value must equal `clients × N` (no lost updates).
- Have clients send across **multiple keys**; verify each key and check cross-key invariants only after quiescence, or use atomic snapshots if checking during updates.
- Deliberately create slow senders/readers, clients that omit newlines, mid-frame disconnects, socket timeouts, and full writer queues; verify that independent clients continue making progress.
- If multiple producers send responses over the same socket, test header/payload interleaving; the peer parser must only see valid frames in the defined order.
- Use `CountDownLatch`/`CyclicBarrier` to synchronize starting points when reproducing races; do not use `Thread.sleep` as proof that all threads have finished.
- Collect lock hold times, CAS retry counts, queue depths, handler counts, socket counts, p95/p99 latencies, and timeouts. Rising throughput paired with anomalous latency spikes for some clients may indicate contention or misconfigured backpressure.

The two programs above verify **exact counts after tasks complete** and **immutable multi-field snapshots**. They do not prove production performance, because client counts, loopback networking, request sizes, and real workloads differ.

## 15. Common Design Mistakes

1. **Synchronizing with `synchronized(server)` around the entire `read/process/write`:** one slow client blocks everyone. Hold locks only around the shared-data region being updated.
2. **Swapping `HashMap` for `ConcurrentHashMap` while still writing `get→put`:** the map structure is safe, but updates can be lost. Use `merge`/`compute`/CAS.
3. **Using `volatile int` for `++`:** visibility does not make read-modify-write atomic. Use `AtomicInteger` or a stronger mechanism.
4. **Using two `AtomicLong`s and expecting a simultaneous snapshot of both:** two `get` calls do not belong to one version. Use immutable state or a short lock.
5. **Reading `LongAdder.sum()` to enforce a strict quota:** the result can change during concurrent updates. Use an appropriate atomic reservation/transaction.
6. **Calling socket/DB inside `compute` or a CAS lambda:** risks blocking, retries, and repeated side effects. Move I/O outside.
7. **Multiple threads writing headers and bodies to the same socket without coordination:** the byte stream can corrupt framing. Use one writer per connection or a per-socket full-frame write lock.
8. **Unbounded queue between handler and writer:** slow clients cause unbounded heap growth. Set capacity and an overload policy.
9. **Failing to release quota in `finally` or releasing it twice:** state drifts on errors/timeouts. Manage reservations by ownership with idempotent cleanup.
10. **Testing with sleep and asserting ordering across sockets:** TCP defines no global order across independent connections. Assert invariants and the protocol order you defined.
11. **Seeing `Future.get()`/ACK and assuming the DB transaction succeeded:** rely on the application's commit/response contract, not the thread pool or TCP.
12. **Holding a read lock while reading and then writing to a socket:** the lock is held across network I/O; copy the needed snapshot and release the lock before I/O.

## 16. Decision Checklist for a TCP Server

Before adding a lock, answer in order:

1. **Which state is truly shared?** Separate socket-local state from user/room/global state.
2. **What is the invariant?** A single counter/key can use an atomic operation; multiple fields/keys may need a transaction or versioned state.
3. **Can the critical section block?** Never place sockets, remote I/O, or unbounded queue waits inside a data lock.
4. **Who writes to a connection?** Only one owner or a mechanism that serializes full frames, with a bounded output queue.
5. **What does the system do under overload?** Bounded concurrency, timeouts, backpressure, and clear cleanup.
6. **What ordering must be guaranteed?** Per connection, per key/room, or global; note that each scope has a different cost.
7. **Have failure cases been checked?** Disconnects, retries, timeouts, cleanup races, full queues, undelivered responses, and mid-update snapshots.

Practical rule of thumb: **network read/write belongs to the connection owner; shared-state updates are small atomic operations matching the invariant; ACK protocols, queues, and connection lifecycles must have clear bounds and ownership**. That way, independent clients can progress in parallel while state correctness remains guaranteed.

API references:
- [Java SE 17 `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [`AtomicLong`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html), [`AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html), and [`LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [`ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`BlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [`Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html), [`ServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html).