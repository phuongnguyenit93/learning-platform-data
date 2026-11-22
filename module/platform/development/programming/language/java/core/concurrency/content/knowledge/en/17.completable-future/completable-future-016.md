# Practical Fan-Out / Fan-In with Multiple I/O Tasks Using CompletableFuture (Java 17+)

## 1. Problem Statement and Learning Outcomes

A request needs to fetch user information from three systems: Profile, Orders, and Inventory. If called sequentially while waiting for each result, the total latency is close to the sum of the API durations. If they are independent, we can issue all three I/O requests first (**fan-out**) and aggregate only once all required results are available (**fan-in**).

~~~text
                    ┌─ HTTP /profile ────> Profile
Request ─ fan-out ───┼─ HTTP /orders ─────> Orders
                    └─ HTTP /inventory ──> Inventory
                                 │
                              fan-in
                                 │
                      Validate / aggregate
                                 │
                         DashboardResponse
~~~

Suppose the independent branches take 120, 180, and 90 ms. Waiting sequentially can be close to `120+180+90=390 ms`; fanning out and waiting for all can be close to `max(120,180,90)=180 ms` **plus overhead**. This is a thought experiment, not a benchmark or latency guarantee. Downstream connection limits, HTTP queueing, CPU, JSON parsing, contention, and retries can all change the outcome.

**Fan-out** is starting multiple units of work that can make progress concurrently; **fan-in** is collecting, validating, and combining outcomes according to a defined policy. There are four common misconceptions: creating multiple Futures does not guarantee multiple I/O operations are running; `allOf` does not return a List; one failing branch does not automatically cancel all remaining branches; and a CompletableFuture timeout/cancel does not automatically roll back remote side effects.

After this lesson, you will be able to:
1. Draw a dependency graph and fan out only truly independent branches.
2. Use `CompletableFuture.supplyAsync` for blocking I/O or `HttpClient.sendAsync` for truly asynchronous HTTP.
3. Combine `allOf`, `thenCombine`, and `thenCompose`, and understand their return types.
4. Decide on required/optional/partial success, and handle exceptions using `handle`, `exceptionally`, and `whenComplete`.
5. Distinguish `get(timeout)`, `orTimeout`, `completeOnTimeout`, HTTP request timeout, and overall deadline.
6. Handle cancellation, late results, retries, and idempotency.
7. Bound fan-out using a semaphore or bounded admission instead of creating unbounded tasks.
8. Control executors and avoid deadlocks caused by blocking waits in the same pool.
9. Run **seven standalone Java 17 programs**, including a real HTTP program over loopback with no Internet dependency.

**Scope:** **CompletableFuture** section, lesson **Practical fan-out / fan-in with multiple I/O tasks**, in **Java Advance - concurrency**. This lesson explains Java SE concurrency in general; it does **not** use Spring-specific APIs or mechanisms, as those have their own chapter.

## 2. Draw the Dependency Graph Before Writing Code

An independent graph:

~~~text
Profile ────────────┐
Orders  ────────────┼── allOf ──> Dashboard
Inventory ──────────┘
~~~

With this graph, sending all three requests close together can reduce total wait time. Do not submit A, call `A.get()`, and only then submit B: that is sequential scheduling wrapped in a Future.

A graph with dependencies:

~~~text
fetchProfile
     |
     +── fetchOrders(profile.id) ──────┐
     |                                 +── Dashboard
     +── fetchStock(profile.region) ───┘
~~~

`fetchOrders` and `fetchStock` need the profile result, so they must wait for profile before starting the two branches. The part after profile can still fan out. Use `thenCompose` to express the dependency relationship.

### Defining the success policy

| Policy | When it makes sense | When a branch fails |
| --- | --- | --- |
| All-required | Every source is mandatory | Aggregate fails with a clear error |
| Optional branch | A part can be missing, e.g. recommendations | Keep status unavailable with a well-defined fallback |
| Best effort | Can return a partial result before the deadline | Return a partial marker; do not pretend it is a full result |
| First usable source | Multiple interchangeable read sources | Need the first **successful** result; do not default to `anyOf` |
| Quorum k-of-n | Result is sufficient when k sources agree/succeed | Dedicated coordinator; `allOf` does not do k-of-n |

This is a business decision. Do not turn an Orders failure into `orders=0` if 0 actually means the customer has placed no orders.

## 3. Essential CompletableFuture Operations

### allOf: waits for all but does not collect values

~~~java
CompletableFuture<A> a = ...;
CompletableFuture<B> b = ...;
CompletableFuture<C> c = ...;

CompletableFuture<Void> all =
        CompletableFuture.allOf(a, b, c);
~~~

This is a snippet with `A/B/C` and the futures already defined. `allOf` completes when all input futures complete; if any future completes exceptionally, the combined future also completes exceptionally. **The value type of `allOf` is `Void`**, not `List<A/B/C>`.

Collecting results after all succeed:

~~~java
CompletableFuture<Dashboard> dashboard =
        CompletableFuture.allOf(profile, orders, inventory)
                .thenApply(ignored -> new Dashboard(
                        profile.join(),
                        orders.join(),
                        inventory.join()));
~~~

This is a snippet, assuming record `Dashboard` and appropriately typed futures. Because the `thenApply` callback only runs after `allOf` succeeds, the `join` calls there read already-completed results; this does not turn it into waiting sequentially for each I/O.

### thenCombine: two independent branches

~~~java
CompletableFuture<Integer> total =
        price.thenCombine(shipping, Integer::sum);
~~~

Assume `price` and `shipping` have already been started independently. `thenCombine` waits for both, then combines them. It **does not submit** the initial suppliers itself.

### thenCompose: next branch depends on the result

~~~java
CompletableFuture<Order> order =
        fetchProfileAsync()
                .thenCompose(profile ->
                        fetchOrderAsync(profile.id()));
~~~

This is a snippet with methods and classes already defined. `thenCompose` flattens the future returned by the callback. If replaced with `thenApply`, the type usually becomes `CompletableFuture<CompletableFuture<Order>>`, i.e., a future containing a future.

### Operator summary table

| Need | Operator |
| --- | --- |
| Combine two independent results | `thenCombine` |
| Wait for N branches | `allOf` |
| Next task needs previous output | `thenCompose` |
| Map a result | `thenApply` |
| Use result or exception to produce another result | `handle` |
| Recover only on exception | `exceptionally` |
| Observe/log completion without recovering by default | `whenComplete` |
| Complete exceptionally on timeout | `orTimeout` |
| Fallback value on timeout | `completeOnTimeout` |
| First completion, success **or failure** | `anyOf` |

## 4. Example 1 — Real HTTP over Loopback with sendAsync and allOf

This example uses JDK 17's `com.sun.net.httpserver.HttpServer` to run three endpoints on `127.0.0.1` with an ephemeral port. `java.net.http.HttpClient.sendAsync` issues three real HTTP requests, rather than only simulating with `Thread.sleep`. No Internet or API key is needed.

**Create file `LocalHttpFanOutDemo.java`:**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class LocalHttpFanOutDemo {
    static void reply(HttpExchange exchange, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    static CompletableFuture<HttpResponse<String>> request(
            HttpClient client, String url) {
        HttpRequest req = HttpRequest.newBuilder(
                URI.create(url)).GET().build();
        return client.sendAsync(
                req, HttpResponse.BodyHandlers.ofString());
    }

    public static void main(String[] args) throws Exception {
        ExecutorService handlers = Executors.newFixedThreadPool(3);
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(handlers);

        server.createContext(
                "/profile", e -> reply(e, "user=42"));
        server.createContext(
                "/orders", e -> reply(e, "orders=3"));
        server.createContext(
                "/inventory", e -> reply(e, "stock=8"));

        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newHttpClient();

            CompletableFuture<HttpResponse<String>> profile =
                    request(client, base + "/profile");
            CompletableFuture<HttpResponse<String>> orders =
                    request(client, base + "/orders");
            CompletableFuture<HttpResponse<String>> inventory =
                    request(client, base + "/inventory");

            CompletableFuture<List<String>> dashboard =
                    CompletableFuture.allOf(
                            profile, orders, inventory)
                    .thenApply(ignored -> List.of(
                            profile.join().body(),
                            orders.join().body(),
                            inventory.join().body()));

            System.out.println("responses="
                    + dashboard.get(5, TimeUnit.SECONDS));
        } finally {
            server.stop(0);
            handlers.shutdownNow();
            handlers.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

**Compile and run on JDK 17+ with the `jdk.httpserver` module:**

~~~bash
javac --add-modules jdk.httpserver LocalHttpFanOutDemo.java
java --add-modules jdk.httpserver LocalHttpFanOutDemo
~~~

Stdout when loopback is permitted and all three requests complete within the time limit:

~~~text
responses=[user=42, orders=3, stock=8]
~~~

Analysis:
1. Port 0 lets the OS assign a free port; response bodies are fixed strings, making output easy to verify.
2. All three `request(...)` calls are made before `dashboard.get`, so the client initiates three asynchronous requests before the fan-in point.
3. `sendAsync` returns futures holding `HttpResponse<String>`; it does not tie up three application worker threads just to call synchronous `HttpClient.send`.
4. `allOf` acts as a barrier; after normal completion, `thenApply` reads `body()` from the three responses in a fixed **logical order**.
5. Whether the Inventory HTTP call finishes earlier or later does not change the `List` order. Response arrival order is not collection order.
6. `main` uses a 5-second timed `get` to avoid waiting indefinitely in the demo. This is a timeout for the **caller waiting on the aggregate**, not a per-HTTP-request deadline or individual cancellation.
7. `finally` stops the loopback server and handler threads; Java 17 code does not call `HttpClient.close()` from later JDK versions.

**Environment note:** This program uses loopback sockets, so a sandbox that forbids opening ports or an overly slow machine may fail to run it. The stdout above is for a normal environment, not a guarantee across every CI setup.

### HTTP status does not mean success

`HttpClient.sendAsync` can complete normally with status 404/500, because an HTTP response was successfully received at the transport level. You must validate it explicitly:

~~~java
CompletableFuture<String> text =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString())
              .thenApply(resp -> {
                  if (resp.statusCode() / 100 != 2) {
                      throw new IllegalStateException(
                              "HTTP " + resp.statusCode());
                  }
                  return resp.body();
              });
~~~

This is a snippet with `client` and `request` already defined. In production you also need to validate schema/JSON, content type, auth, body size, retryability, and correlation ID. If you only call `allOf` and take `body()`, an HTTP 500 can be mistaken for valid business data.

## 5. Example 2 — Proving Three I/O Tasks Wait Concurrently Using CountDownLatch

The following example simulates I/O to verify **task concurrency** without needing sockets. All three tasks enter the wait region before `main` opens the latch. This is a coordination test, not a real speed measurement.

**Create file `SimulatedIoFanOutDemo.java`:**

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class SimulatedIoFanOutDemo {
    static String waitForRelease(
            CountDownLatch started,
            CountDownLatch gate,
            String value) {
        started.countDown();
        try {
            gate.await();
            return value;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new CompletionException(e);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService io = Executors.newFixedThreadPool(3);
        CountDownLatch started = new CountDownLatch(3);
        CountDownLatch gate = new CountDownLatch(1);

        try {
            CompletableFuture<String> a =
                    CompletableFuture.supplyAsync(() ->
                            waitForRelease(started, gate, "profile"), io);
            CompletableFuture<String> b =
                    CompletableFuture.supplyAsync(() ->
                            waitForRelease(started, gate, "orders"), io);
            CompletableFuture<String> c =
                    CompletableFuture.supplyAsync(() ->
                            waitForRelease(started, gate, "stock"), io);

            started.await();
            gate.countDown();

            CompletableFuture<List<String>> result =
                    CompletableFuture.allOf(a, b, c)
                    .thenApply(ignored ->
                            List.of(a.join(), b.join(), c.join()));

            System.out.println("values=" + result.join());
            System.out.println("allDone=" +
                    (a.isDone() && b.isDone() && c.isDone()));
        } finally {
            gate.countDown();
            io.shutdownNow();
            io.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac SimulatedIoFanOutDemo.java
java SimulatedIoFanOutDemo
~~~

Stdout when there is no external interruption:

~~~text
values=[profile, orders, stock]
allDone=true
~~~

**Why is this result reliable?**
- The pool has three workers, enough for all three tasks to enter `gate.await()`.
- Each task calls `started.countDown()` before waiting; `main` only releases the gate after all three signals arrive.
- Only then can the worker tasks return values, and `allOf` waits for all three.
- Results are listed in `a,b,c` order, **not** in the order threads woke up.
- `Future.join()` after `allOf` completes normally only reads already-finished results; it does not create a sequential I/O wait chain.

### Anti-pattern: calling join immediately after each launch

~~~java
String a = CompletableFuture.supplyAsync(
        this::loadA, ioPool).join();
String b = CompletableFuture.supplyAsync(
        this::loadB, ioPool).join();
String c = CompletableFuture.supplyAsync(
        this::loadC, ioPool).join();
~~~

This is a snippet inside a class with `loadA/B/C` and `ioPool`. B is only submitted **after A finishes**, and C is only submitted after B. Despite using CompletableFuture, actual execution is nearly sequential.

The right way is to **start all independent branches first, and fan in afterward**:

~~~java
CompletableFuture<String> a =
        CompletableFuture.supplyAsync(this::loadA, ioPool);
CompletableFuture<String> b =
        CompletableFuture.supplyAsync(this::loadB, ioPool);
CompletableFuture<String> c =
        CompletableFuture.supplyAsync(this::loadC, ioPool);

CompletableFuture<List<String>> result =
        CompletableFuture.allOf(a, b, c)
        .thenApply(v -> List.of(
                a.join(), b.join(), c.join()));
~~~

This is also just a snippet illustrating dependency structure.

## 6. Single-Branch Failure: All-Required or Partial Success?

When a downstream service is unavailable:
- A `CompletableFuture` can complete exceptionally.
- `allOf` completes exceptionally if at least one input is exceptional (it does not turn errors into defaults).
- A `thenApply` depending on `allOf` succeeding **does not run** when the aggregate fails.
- `allOf` does not automatically cancel all siblings just because one branch failed.
- Sibling requests that have already started may continue doing I/O, consuming network resources, or producing side effects.

Before writing recovery logic, classify each branch:
- **Required:** missing this branch means the request is no longer valid; the aggregate must report failure.
- **Optional:** missing this branch still allows a valid response, but the source must be marked unavailable.
- **Partial:** store per-branch outcomes, not only successful values.

### Example 3 — Partial result without hiding errors

**Create file `PartialFanInDemo.java`:**

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class PartialFanInDemo {
    record Slot(String source, String value, String error) {
        @Override
        public String toString() {
            return source + "="
                    + (error == null ? value : "ERR:" + error);
        }
    }

    public static void main(String[] args) {
        ExecutorService io = Executors.newFixedThreadPool(3);
        try {
            CompletableFuture<String> profile =
                    CompletableFuture.supplyAsync(
                            () -> "user=42", io);
            CompletableFuture<String> orders =
                    CompletableFuture.supplyAsync(() -> {
                        throw new IllegalStateException("HTTP_503");
                    }, io);
            CompletableFuture<String> stock =
                    CompletableFuture.supplyAsync(
                            () -> "stock=8", io);

            CompletableFuture<Slot> p = profile.handle(
                    (v, e) -> new Slot(
                            "profile", v,
                            e == null ? null : "unavailable"));
            CompletableFuture<Slot> o = orders.handle(
                    (v, e) -> new Slot(
                            "orders", v,
                            e == null ? null : "unavailable"));
            CompletableFuture<Slot> s = stock.handle(
                    (v, e) -> new Slot(
                            "stock", v,
                            e == null ? null : "unavailable"));

            CompletableFuture<List<Slot>> partial =
                    CompletableFuture.allOf(p, o, s)
                    .thenApply(x -> List.of(
                            p.join(), o.join(), s.join()));

            System.out.println("partial=" + partial.join());

            CompletableFuture<Void> strict =
                    CompletableFuture.allOf(
                            profile, orders, stock);
            try {
                strict.join();
            } catch (CompletionException e) {
                System.out.println("strictError="
                        + e.getCause().getClass().getSimpleName());
            }
        } finally {
            io.shutdownNow();
            try {
                io.awaitTermination(1, TimeUnit.MINUTES);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

Run:

~~~bash
javac PartialFanInDemo.java
java PartialFanInDemo
~~~

Stdout:

~~~text
partial=[profile=user=42, orders=ERR:unavailable, stock=stock=8]
strictError=IllegalStateException
~~~

Explanation:
1. `orders` throws `IllegalStateException`, so the original Future becomes exceptional.
2. `handle` runs on both success and error; it returns a normal `Slot` containing an explicit status. `handle` **does not change the state of the original future**.
3. `allOf(p,o,s)` receives three normal futures and collects three `Slot`s in source order.
4. `allOf(profile,orders,stock)` still fails; `join()` on the strict aggregate throws `CompletionException` with the cause from `orders`.
5. Both aggregation styles share the same I/O group, but have different business policies.

**Distinguishing error-handling operators:**
- `handle((v,e)->r)`: runs on both success/error and can transform to type `R`.
- `exceptionally(e->fallback)`: recovers only on error and keeps the same type.
- `whenComplete((v,e)->log(...))`: observes the outcome without recovering by default.
- `exceptionallyCompose(...)`: recovers using a new Future, available in Java 17.

Do not use `exceptionally(ex -> null)` indiscriminately: `null` can be misinterpreted as real data or cause an NPE at the aggregation layer. If Orders fails, do not turn it into `orders=0` unless the domain truly specifies that as a valid fallback.

## 7. Example 4 — Expressing a Graph with thenCombine and thenCompose

Shipping cost does not depend on product price: fetch price and shipping in parallel, then compute the total; only once the total is available, create a receipt. This is an example of a small fan-out + dependent stage.

**Create file `CompositionGraphDemo.java`:**

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompositionGraphDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService io = Executors.newFixedThreadPool(3);
        try {
            CompletableFuture<Integer> price =
                    CompletableFuture.supplyAsync(
                            () -> 120, io);
            CompletableFuture<Integer> shipping =
                    CompletableFuture.supplyAsync(
                            () -> 15, io);

            CompletableFuture<Integer> total =
                    price.thenCombine(
                            shipping, Integer::sum);

            CompletableFuture<String> receipt =
                    total.thenCompose(value ->
                            CompletableFuture.supplyAsync(
                                    () -> "total=" + value, io));

            System.out.println("receipt=" + receipt.get());
        } finally {
            io.shutdown();
            io.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac CompositionGraphDemo.java
java CompositionGraphDemo
~~~

Stdout:

~~~text
receipt=total=135
~~~

`price` and `shipping` are started first; `thenCombine` waits for both and computes 135; `thenCompose` runs only once `total` is ready and flattens the new Future. If the next step is an async HTTP request, the callback can directly return `client.sendAsync(...)` instead of using `supplyAsync`.

**Avoiding deadlock:** Do not block a worker with `otherFuture.join()` if `otherFuture` can only run on **the same single-threaded executor** and is sitting in the queue behind that worker. Express dependencies via composition instead of making a busy worker wait on a task that has not started yet.

## 8. Setting Timeouts Properly at Three Layers

**Layer 1 — caller wait timeout:** `future.get(300, MILLISECONDS)` bounds how long the caller waits. On `TimeoutException`, the task may still be running; `get(timeout)` does not automatically call cancel.

**Layer 2 — CompletableFuture completion timeout:**
- `orTimeout(t,u)` completes the Future exceptionally with `TimeoutException` if not completed before the deadline.
- `completeOnTimeout(fallback,t,u)` completes the Future with a fallback if not completed before the deadline.

Both methods affect **the state of the CompletableFuture itself** and are not a system command to stop all underlying I/O.

**Layer 3 — transport timeout:** `HttpClient.Builder.connectTimeout`, `HttpRequest.Builder.timeout`, or the timeout of the actual JDBC/driver/socket/SDK. These have their own semantics and must be tuned to the request deadline.

### Example 5 — completeOnTimeout does not force the worker to exit

**Create file `TimeoutNotStopDemo.java`:**

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class TimeoutNotStopDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService io = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        try {
            CompletableFuture<String> request =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "REAL_RESPONSE";
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            throw new CompletionException(e);
                        } finally {
                            exited.countDown();
                        }
                    }, io);

            started.await();
            request.completeOnTimeout(
                    "FALLBACK", 20, TimeUnit.MILLISECONDS);

            String visible = request.join();

            release.countDown();
            exited.await();

            System.out.println("visible=" + visible);
            System.out.println("workerExited=" +
                    (exited.getCount() == 0));
            System.out.println("futureValue=" + request.join());
        } finally {
            release.countDown();
            io.shutdownNow();
            io.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac TimeoutNotStopDemo.java
java TimeoutNotStopDemo
~~~

Stdout with no external interruption:

~~~text
visible=FALLBACK
workerExited=true
futureValue=FALLBACK
~~~

Because `release` has not been lowered, the supplier cannot return `REAL_RESPONSE` before the timeout. The Future receives `FALLBACK` and `join` returns right after the deadline. **The worker is still waiting** until `main` lowers the latch. `main` waits for `exited` afterward, but the Future's outcome does not change. If `orTimeout` is used instead of `completeOnTimeout`, `join()` will throw `CompletionException` with cause `TimeoutException` when the deadline wins.

### End-to-end deadline

Do not grant a fresh 500 ms to each stage within the same request if the caller only has a 500 ms total budget. Carry the remaining duration to APIs that accept timeouts. For duration measurements within a single JVM, `System.nanoTime()` can be used; it is not a UTC timestamp to send as-is to another process. If remaining <= 0, do not initiate new I/O just to let it time out.

### HTTP request timeout

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest req = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(3))
        .GET().build();

CompletableFuture<HttpResponse<String>> response =
        client.sendAsync(
                req, HttpResponse.BodyHandlers.ofString());
~~~

This is a snippet with imports `java.time.Duration`, `java.net.http.*`, and `java.net.URI`, and variable `uri` defined. Timeouts on the HTTP API have their own scope; an overall request deadline/cancel policy is still required.

## 9. Cancellation and Still-Running I/O

In Java 17, `CompletableFuture.cancel(true)` **does not use `mayInterruptIfRunning` to control execution** the way some `FutureTask` implementations do. It can transition the CompletableFuture to cancelled, but **does not guarantee** that the `supplyAsync` runner is interrupted.

In fan-out:
- Cancelling the aggregate Future does not automatically cancel every branch.
- Siblings that have already started may keep running.
- Downstream callbacks that have not run yet may receive exceptional completion due to cancellation.
- A remote service may have already written data before the caller decided to cancel.
- When retrying, use an idempotency key/reconciliation if there are side effects.
- To actually cancel I/O, use the corresponding timeout, close, or cancellation handle **on the client API**.

A note on `HttpClient.sendAsync`: the Future returned by the HTTP client has transport-specific cancellation behavior; the implementation may attempt to cancel the HTTP exchange when you call cancel. However, there is no guarantee the remote server rolled back data it already received. Do not infer from `isCancelled()==true` that “the request was never processed”.

### Example 6 — cancel(true) does not necessarily interrupt a supplyAsync runner

**Create file `CancelIsNotInterruptDemo.java`:**

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelIsNotInterruptDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService io = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "REAL";
                        } catch (InterruptedException e) {
                            interrupted.set(true);
                            Thread.currentThread().interrupt();
                            throw new CompletionException(e);
                        } finally {
                            exited.countDown();
                        }
                    }, io);

            started.await();
            boolean accepted = future.cancel(true);

            release.countDown();
            exited.await();

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("cancelled=" + future.isCancelled());
            System.out.println("interrupted=" + interrupted.get());
            System.out.println("workerExited=" + (exited.getCount() == 0));

            try {
                future.join();
            } catch (CancellationException e) {
                System.out.println("join=CancellationException");
            }
        } finally {
            release.countDown();
            io.shutdownNow();
            io.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac CancelIsNotInterruptDemo.java
java CancelIsNotInterruptDemo
~~~

Stdout with a standard executor and no external interrupt:

~~~text
cancelAccepted=true
cancelled=true
interrupted=false
workerExited=true
join=CancellationException
~~~

`main` cancels the Future while the worker is waiting on the latch. `cancel(true)` marks the Future cancelled but **does not interrupt** the supplier per the Java 17 CompletableFuture contract. `main` then actively lowers the latch, and the worker actually exits. `join` receives `CancellationException`, even though the worker could have returned `REAL` afterward. This illustrates the boundary that **future outcome** is distinct from **worker lifecycle**.

## 10. Bounding Fan-Out and Backpressure

Naive code:

~~~java
List<CompletableFuture<Response>> tasks = ids.stream()
        .map(id -> CompletableFuture.supplyAsync(
                () -> blockingRemoteCall(id), ioPool))
        .toList();
~~~

This is a snippet with `Response` and application-defined methods/variables. If `ids` contains 100,000 elements, you can create 100,000 Future objects and 100,000 queued tasks. A fixed thread pool limits **workers**, but a standard `Executors.newFixedThreadPool(n)` uses an unbounded queue; it **does not bound the backlog**.

Distinguish among:
- **In-flight concurrency limit:** at most K active remote calls.
- **Admission/queue bound:** at most Q accepted requests not yet running.
- **Rate limit:** at most N initiated calls per time window.
- **Deadline:** wait time / total time for a request.
- **Bulkhead:** isolating downstream/resource groups so one weak service does not block all services.

`Semaphore` can limit active calls, but if acquired **inside every task after submission**, a huge number of Futures/tasks still occupy queue and memory. For production, limit **before submission**, split into batches, or build a bounded dispatcher/async semaphore.

### Example 7 — Bounded in-flight with Semaphore

**Create file `BoundedFanOutDemo.java`:**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedFanOutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService io = Executors.newFixedThreadPool(4);
        Semaphore permits = new Semaphore(2);
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger maxObserved = new AtomicInteger();
        List<CompletableFuture<Integer>> tasks = new ArrayList<>();

        try {
            for (int i = 1; i <= 6; i++) {
                final int id = i;
                tasks.add(CompletableFuture.supplyAsync(() -> {
                    boolean acquired = false;
                    try {
                        permits.acquire();
                        acquired = true;

                        int count = inFlight.incrementAndGet();
                        maxObserved.accumulateAndGet(count, Math::max);

                        Thread.sleep(10); // Simulate I/O wait.
                        return id * id;
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new CompletionException(e);
                    } finally {
                        if (acquired) {
                            inFlight.decrementAndGet();
                            permits.release();
                        }
                    }
                }, io));
            }

            CompletableFuture.allOf(
                    tasks.toArray(new CompletableFuture<?>[0]))
                    .join();

            int total = tasks.stream()
                    .mapToInt(CompletableFuture::join)
                    .sum();

            System.out.println("sumSquares=" + total);
            System.out.println("withinLimit=" +
                    (maxObserved.get() <= 2));
            System.out.println("permitsRestored=" +
                    permits.availablePermits());
        } finally {
            io.shutdownNow();
            io.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac BoundedFanOutDemo.java
java BoundedFanOutDemo
~~~

Stdout independent of worker order:

~~~text
sumSquares=91
withinLimit=true
permitsRestored=2
~~~

Six branches compute `1²+2²+3²+4²+5²+6²=91`. Only a task that has acquired a permit increments `inFlight`; `Semaphore(2)` guarantees `maxObserved<=2`. The actual peak **can be 1 or 2** depending on scheduling, so a fixed peak number is not printed. Permits are released in `finally` and `main` checks after `allOf`.

**Demo limitation:** `Thread.sleep` simulates waiting and acquires inside the worker; this pattern does not bound the number of submitted Futures yet. With real HTTP `sendAsync`, check connection limits and use bounded admission before issuing `n` requests.

## 11. Dynamic Future Lists and Empty Input

When the number of branches varies per request, the typical collection pattern is:

~~~java
List<CompletableFuture<Item>> futures =
        ids.stream()
           .map(id -> fetchItemAsync(id))
           .toList();

CompletableFuture<List<Item>> combined =
        CompletableFuture.allOf(
                futures.toArray(new CompletableFuture<?>[0]))
        .thenApply(ignored ->
                futures.stream()
                       .map(CompletableFuture::join)
                       .toList());
~~~

This is a snippet with `Item`, `ids`, and `fetchItemAsync` defined. `List.toList()` follows the **encounter order of the input futures**, not the completion order.

`CompletableFuture.allOf()` with zero arguments completes normally, so an empty List can become a valid empty result. However, if `ids` has hundreds of thousands of elements, do not eagerly create all Futures. Split into batches with a policy on total in-flight work and backlog.

## 12. anyOf Does Not Mean First-Success

`CompletableFuture.anyOf(a,b,c)` completes with the **first completion**, including an exceptional one. If the fastest source returns HTTP 503, `anyOf` can complete exceptionally even though a slower source would succeed. This **does not** satisfy a “get the earliest successful result” policy.

For true first-success:
- A coordinator tracks failures and successes of each candidate.
- The first normal completion wins; only if **all** fail does it report failure.
- Once one source wins, apply a policy to the losers: continue/stop, cleanup, late side effects.
- Cap concurrent requests and the cost of duplicate calls.
- If operations are writes, do not fan out the same transaction to multiple places and pick the first result without an idempotency/transaction policy.

Do not use `applyToEither` or `anyOf` as a general-purpose first-success abstraction without carefully reading their exceptional completion semantics.

## 13. Callback Threading and Starvation Risks

`thenApply`, `handle`, and `thenCombine` without the `Async` suffix can run the callback on the thread that completed the previous stage or on the thread calling completion, depending on timing/contract. Do not assume the callback runs on `main` or on a new executor.

`thenApplyAsync(fn, executor)` schedules the callback on the executor you choose. It is useful when the callback performs **CPU-heavy parsing**, though it also adds scheduling overhead:
- Combining a few immutable records very quickly: `thenApply` is usually appropriate.
- Heavy JSON parsing, decoding/compression: consider `thenApplyAsync` in a CPU pool.
- Blocking legacy API: run on a dedicated bounded I/O executor or use a truly async API.
- Do not use `Async` just because of the word “async”: it does not make a `Thread.sleep` nonblocking.

### Avoid waiting on a Future that needs the very worker currently blocked

~~~text
Single-thread executor:
  Worker is running A and calls B.join()
  B is still in the queue behind A
  -> B has no worker to run on -> can deadlock
~~~

`CompletableFuture` is designed to express dependencies with `thenCompose`/`thenCombine`, instead of holding a worker in an unnecessary blocking `get/join`.

## 14. Timeouts, Retries, and Idempotency with Remote Services

A request with a 700 ms deadline and three downstreams should not give each branch a fresh **700 ms from when it starts** if it still depends on two other stages. Propagate the deadline/remaining budget across the entire graph.

Within one JVM, `System.nanoTime()` can measure duration; do not send a raw `nanoTime` value to another JVM as a UTC timestamp. Pass appropriate timeouts into HTTP requests/connections and downstream APIs.

When retrying:
- Retry only errors classified as retryable.
- Consider exponential backoff, jitter, retry budget, and max attempts.
- Split the total time budget across attempts.
- Protect downstreams from retry storms when many incoming requests time out simultaneously.
- For write operations, use an idempotency key on the receiver to avoid duplicate side effects.

**Example:** Client sends `createOrder`, server commits, but the response is slow. Caller times out and retries. A `CompletableFuture` timeout does not tell you whether the previous order was created; without idempotency/reconciliation, duplicate orders can be created.

## 15. Performance Measurement and Pipeline Observability

Do not measure speedup with a single `System.currentTimeMillis()`. I/O latency fluctuates with DNS, connection reuse, OS scheduler, TLS, server load, GC, retries, and network conditions.

Recommended metrics:
- End-to-end request latency (p50/p95/p99).
- Per-branch latency and HTTP status/errors.
- In-flight calls per downstream.
- Thread pool active count, queue wait, saturation/rejection.
- Timeout counts broken down by caller/CF/transport.
- Fallback/partial-success rates, kept separate from full success.
- Cancellation requested vs. underlying I/O completion/cleanup.
- Total request attempts after retries and idempotency collisions.
- Backlog and memory/connection limits.
- Spread from fastest branch to slowest branch.

**Test plan:**
1. Sequential baseline on the same three endpoints with the same inputs.
2. Fan-out of three independent branches, no retries; observe latency.
3. Test a 10x slower branch, HTTP 500 error branch, timeout, and malformed JSON.
4. Test partial policy and all-required policy; verify response schema.
5. Test high concurrency; measure downstream saturation and queue memory.
6. Cancel a request while all branches are still running; verify cleanup/late responses.
7. Test failure of one sibling while other siblings are waiting.
8. Set realistic connection/rate limits instead of benchmarking against an unlimited mock server.
9. Do not put fixed timing numbers in example outputs because scheduling is not guaranteed.
10. For CPU-only microbenchmarks, use JMH; for end-to-end I/O, use proper load testing.

## 16. Common Pitfalls and How to Fix Them

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| `join` after each `supplyAsync` | Turns fan-out into sequential execution | Launch all first, fan in afterward |
| Assuming `allOf` returns a List | Type mismatch | Build the List in a dependent stage after `allOf` |
| Branch fails yet expecting `thenApply` to run normally | It does not run; aggregate is exceptional | Handle errors per branch per policy |
| `exceptionally(ex -> null)` everywhere | Hides errors/NPEs or reports fake success | Use explicit result/error markers |
| Treating HTTP 500 as a normal business response | Reports wrong data | Validate status/schema |
| Using `thenApply` to return a CompletableFuture | Nested Future inside Future | Use `thenCompose` |
| Wrapping `sendAsync` in blocking `supplyAsync` | Wastes threads waiting on I/O | Use async HttpClient directly |
| Blocking I/O on the default common pool | Starvation/contended pool | Dedicated bounded I/O executor |
| Assuming FixedThreadPool has a bounded queue | Backlog/future memory can grow unbounded | Bounded admission/queue |
| Acquiring Semaphore after submitting huge task counts | Limits in-flight work but not queue size | Limit before submission or batch |
| Using `anyOf` for first-success | First failure can win | Use a first-success coordinator |
| Assuming `get(timeout)` auto-cancels | Underlying task can still run | Cancel/clean up explicitly |
| Assuming `orTimeout` cancels the socket | Remote I/O may continue | Set timeouts on the transport API |
| Assuming `CompletableFuture.cancel(true)` interrupts runner | Not guaranteed | Track task/transport handles |
| Assuming one failing branch stops all siblings | Orphan work/side effects | Ownership/cancellation policy |
| Uncontrolled retries | Amplifies traffic when downstream fails | Retry budget/backoff/jitter |
| Returning partial as full success | Wrong domain semantics | Per-branch markers |
| Heavy JSON parsing on completion thread | Increases callback latency | Dedicated CPU executor |
| Waiting on sibling Future on a single-thread pool | Thread starvation deadlock | Non-blocking composition |
| Reading results in completion order when key order is needed | Unstable response | Collect in input/key order |
| Treating local Future cancel as remote write rollback | Duplicates on retry | Idempotency/reconciliation |
| Confusing worker exited with `isDone` | Misjudges cleanup | Separate lifecycle signal |
| Shutting down a shared executor at end of one request | Breaks other requests | Service owns executor lifecycle |

## 17. Production Checklist

1. Which branches are truly independent, and which need a previous branch's output?
2. Are all child futures launched before the fan-in point?
3. Are the `allOf` return type and collection logic correct?
4. Is sorted/key order required, or is completion order acceptable?
5. Are HTTP status and body schema validated?
6. Error policy: all-required, optional, partial, or first-success?
7. Do optional fallbacks have an explicit marker that avoids domain ambiguity?
8. What is the maximum number of children per request?
9. Is total in-flight work per downstream/tenant bounded?
10. Is executor queue/admission bounded?
11. Is there an overall deadline in addition to connection/request timeouts?
12. Are CF timeouts being mistaken for stopping I/O?
13. Who holds cancel handles and performs cleanup when a request is cancelled?
14. Can late results overwrite newer state?
15. Do remote writes have idempotency on retry?
16. Is the callback lightweight or CPU-heavy, and which executor does it need?
17. Is there any blocking `join`/`get` inside the very pool needed to complete the future?
18. If one branch fails while siblings are still running, what is the policy?
19. Do results from multiple sources need the same epoch/version?
20. Are branch latency, exception, timeout, and backlog metrics collected?
21. Are partial/error/cancel/timeout race conditions tested?
22. Are executors shut down by the proper owner without creating/leaking a pool per branch?
23. Does an empty input list return a valid result?
24. Are environment CPU/RAM/connection quotas factored into capacity?

## 18. Self-Check

1. **What is fan-out?** Starting multiple independent units of work that can progress concurrently.
2. **What is fan-in?** Synchronizing and aggregating the outcomes of those units of work.
3. **Does `allOf` return a List?** No, it returns `CompletableFuture<Void>`.
4. **How do you collect a List of results after `allOf`?** `thenApply` and `join` on the already-completed children.
5. **When is `thenCombine` appropriate?** When two independent futures need to be combined after both finish.
6. **When is `thenCompose` appropriate?** When the next stage depends on the previous result and returns a Future.
7. **What does calling `join` after each launch cause?** It can serialize the fan-out.
8. **If one child fails, what happens to `allOf`?** It completes exceptionally; it does not automatically cancel siblings.
9. **Should a failed Orders call fall back to `orders=0`?** Not if 0 is valid domain data and unavailable is distinct from 0.
10. **Does `HttpClient.sendAsync` throw automatically on status 500?** Not necessarily; validate the status.
11. **In what order is the list produced in `thenApply` after `allOf`?** In collection code order, not completion order.
12. **Does `Future.get(timeout)` automatically cancel?** No.
13. **Does `completeOnTimeout` interrupt a blocking supplier?** Not guaranteed.
14. **Does `CompletableFuture.cancel(true)` guarantee interrupting the runner?** No.
15. **Does cancelling an HTTP request guarantee remote rollback?** No.
16. **Does a fixed pool of 4 workers limit the queue to 4 tasks?** No.
17. **What does `Semaphore(2)` protect?** At most two permit holders concurrently.
18. **Does a Semaphore inside the task after submission bound the number of waiting Futures?** No.
19. **Does `anyOf` wait for the first successful result?** No; the first failure can also complete it.
20. **Do `thenApply` callbacks always run on the main thread?** No.
21. **What can a CPU-heavy stage use?** `thenApplyAsync(fn,cpuPool)`.
22. **When is a blocking `get` in a single-thread pool dangerous?** When the Future needs that same pool to run.
23. **Why is an overall deadline needed?** To avoid granting a full timeout budget to every stage.
24. **Where is retrying a remote POST after a timeout dangerous?** The previous request may have already committed, creating a duplicate.
25. **How do Future `isDone` and worker exited differ?** `isDone` can happen due to cancel/timeout before the task actually stops.
26. **Does measuring fan-out guarantee a speedup?** No; it depends on downstream capacity and overhead.
27. **When is a partial result valid?** When the business contract can represent unavailable separately.
28. **How do you avoid fake success?** Per-branch `Result`/`Slot` holding explicit value/error.
29. **What does `allOf` do when there are no ids?** `allOf()` is already completed normally.
30. **What is the core of reliable I/O fan-out?** Correct dependency graph, bounded load, deadline/failure policy, cleanup, and idempotency.

## 19. Conclusion

**Effective fan-out / fan-in is more than calling `supplyAsync` three times.** It requires a sound task graph, clear result policies, and appropriate resource limits:

~~~text
Fan-out: start independent requests
               |
               v
Fan-in: allOf / thenCombine
               |
               v
Check HTTP status, timeout, failure, fallback
               |
               v
Build aggregate / publish with ownership policy
~~~

Use `thenCompose` for dependencies, `allOf` to wait on multiple branches, and `thenCombine` for two independent branches. Collect results in business order. Define required/optional branches and do not arbitrarily turn errors into valid data. **A timeout/cancel on a Future is not proof that remote I/O has stopped or rolled back**. You need bounded concurrency/admission, bounded retries, idempotency for remote writes, and per-branch metrics.

With Java 17, `HttpClient.sendAsync` provides asynchronous HTTP I/O, while `CompletableFuture` expresses coordination; decisions about deadlines, cancellation, backpressure, and business correctness remain the application's design responsibility.

## Java SE 17 References

- [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `allOf`, `thenCombine`, `thenCompose`, `handle`, `orTimeout`, `completeOnTimeout`, `cancel`.
- [CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): dependent stages model.
- [HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `sendAsync` and connect timeout.
- [HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request timeout.
- [HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): status and body.
- [HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback HTTP example.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): worker and lifecycle.
- [Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): bounded in-flight work.
- [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): concurrency testing.
- [ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool and work stealing.
