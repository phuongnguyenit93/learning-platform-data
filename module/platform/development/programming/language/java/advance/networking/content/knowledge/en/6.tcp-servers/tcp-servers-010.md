# Testing Multiple Concurrent Connections and Cleaning Up Resources on Failure

## 1. Why Must a TCP Server Be Tested for Both Concurrency and Failure?

A TCP server can accept multiple connections at the same time. **ServerSocket.accept()** returns a **new Socket** for each connection, while the ServerSocket continues its listening role. The server then assigns the socket to a worker to read the request, process it, write the response, and close the connection.

For example, when eight clients arrive close together:

~~~text
                     ServerSocket (listening)
                                |
                           accept()
                                |
        +-----------------------+----------------------+
        |                       |                      |
    Socket A                 Socket B               Socket C  ...
        |                       |                      |
     Worker A                Worker B                Worker C
    succeeds             throws exception            succeeds
        |                       |                      |
   close Socket A          close Socket B          close Socket C
                                |
                       server still serves A, C
~~~

Two important criteria:

- **Correctness under concurrency:** requests/responses are not mixed up, multiple handlers actually process concurrently in an overlapping manner, the server has resource limits, and a slow or failing request does not stall all other requests.
- **Correctness under failure:** even when an IOException, RuntimeException, read timeout, client disconnection, executor task rejection, or server shutdown occurs, someone is still responsible for closing the socket and executor; no threads, tasks, or resources are left behind.

Running eight requests **sequentially** and seeing all eight responses does not prove the server serves concurrently. Starting eight clients **at the same time** is also not enough: the server could still process them one by one. A test needs a synchronization point to prove that **at least two handlers are in the processing region at the same time**.

## 2. Defining the Resource Contract and Invariants to Verify

Resources must have a **clear owner**:

| Resource | Who owns it? | When must it be released? |
| --- | --- | --- |
| **ServerSocket** | Server management component | When the server stops accepting connections |
| **Socket returned by accept** | Worker after successful submission | When the request succeeds **or** fails |
| **Accepted Socket not yet handed off to a worker** | Accept loop | Immediately when the executor rejects the task |
| **Read/write streams** | Handler via Socket | End of session; closing the Socket also closes its corresponding streams |
| **ThreadPoolExecutor** | Server | Shutdown, wait for termination, handle stuck tasks |
| **Accept loop thread** | Server | After the listener closes and the thread terminates |
| **Client-side Socket** | Client/test task | try-with-resources even when the test fails |
| **ExecutorService running client tests** | Test harness | finally: shutdown and awaitTermination |

Some **invariants** to track:

- **accepted:** total Sockets accepted.
- **active:** number of currently running handlers; must return to **0** at the end of the test.
- **peakActive:** maximum number of concurrent handlers; to prove concurrency, it must be **≥ 2**.
- **successful / failed:** controlled count of successful/failed executions. Each handler must be recorded **exactly once**.
- **closed:** number of server-side Sockets closed according to API state.
- **finished:** number of handlers that reached the end of their lifecycle; must match the scenarios that received ownership.
- **terminated:** worker pool and coordinator threads terminated after shutdown.

**accepted does not automatically equal successful**: a connection may fail before sending a request, be overloaded, or be sitting in the queue. **Socket.isClosed()** only confirms that the JVM-side Socket object is closed; it does not by itself prove that the peer received/committed the response or that all kernel TCP states have disappeared.

### Transferring Ownership After accept

Error-prone code:

~~~java
// WRONG: the accept loop closes the socket as soon as it exits the block,
// even though the worker may still be processing it.
try (Socket peer = listener.accept()) {
    pool.execute(() -> handle(peer));
}
~~~

Code with correct ownership:

~~~java
// Illustration; listener, pool variables and handle method are already declared.
Socket peer = listener.accept();
try {
    pool.execute(() -> handle(peer)); // Worker takes ownership.
} catch (RejectedExecutionException ex) {
    peer.close(); // Submission failed: the accept loop still owns the socket.
    throw ex;
}
~~~

And the handler owns the socket:

~~~java
// Method illustration; Java 17 allows using effectively final variables.
static void handle(Socket peer) throws IOException {
    try (peer) {
        // Read, process, respond.
    } // Java closes the Socket on success or when an exception is thrown.
}
~~~

In a real system, log socket close errors, persist request state, and handle suppressed exceptions when needed. Do not increment the **closed** counter right at accept, because at that point the resource has not been closed at all.

## 3. Common Concurrency Architecture in Java 17

~~~text
acceptor thread
    |
ServerSocket.accept()
    |
    +-- Socket 1 ----\
    +-- Socket 2 -----+--> ThreadPoolExecutor
    +-- Socket 3 ----/       |             |
    +-- Socket N          workers     bounded queue
                            |
                         handler
                            |
                    try-with-resources
                            |
                       close socket
~~~

With a fixed pool of four workers, at most **four handlers** work concurrently. Other tasks can wait in the queue. A bounded queue prevents unbounded buildup. If both workers and queue are full, **execute() can throw RejectedExecutionException**.

Relevant APIs:

- **ServerSocket(0, backlog, loopback):** uses an OS-chosen port; tests retrieve the actual port via **getLocalPort()**, avoiding fixed-port conflicts on CI.
- **ExecutorService / ThreadPoolExecutor:** executes handlers in a controlled manner and manages their lifecycle.
- **CountDownLatch:** makes multiple clients start together, or holds handlers at a synchronization point to prove overlap.
- **Future.get(timeout):** waits for each client to complete and detects stuck tasks.
- **AtomicInteger:** safely counts active, peakActive, successful, failed, and closed across multiple workers.
- **Socket.setSoTimeout(n):** limits the blocking time of a read operation; **not an overall request deadline**.
- **try-with-resources:** guarantees calling close() on the socket whether the code throws IOException or RuntimeException.

### Why Is Using Only Thread.sleep() a Poor Test?

~~~java
// Poor testing practice: sleep does not prove handlers run concurrently.
startClients();
Thread.sleep(100);
check(serverIsConcurrent());
~~~

On slow CI, 100 ms may be too short; on a fast machine, the result may pass by coincidence. Replace it with an **explicit barrier/latch and timeout**:

~~~java
// Inside handler:
twoActive.countDown();
letHandlersRun.await();

// Inside test thread:
require(twoActive.await(10, TimeUnit.SECONDS),
        "fewer than 2 handlers started");
letHandlersRun.countDown();
~~~

When two handlers have both decremented the latch, but have not yet been released, the test **knows that two handlers exist concurrently in the processing region**. The latch must also be released in **finally** to avoid deadlock if an earlier assertion fails.

## 4. Runnable Java 17+ Integration Program

This program is a **self-contained integration test**, requiring no JUnit, Maven, external services, or Internet:

1. The server binds loopback TCP on an ephemeral port assigned by the OS.
2. Eight client tasks wait on a latch and then start almost simultaneously.
3. The server uses **4 workers**, a bounded queue holding at most eight tasks, waits for at least two handlers to enter the processing region, and then releases them.
4. Six clients send requests **C2** through **C7** and receive the exact responses **ACK:C2** through **ACK:C7**.
5. Two clients send **FAIL_IO** and **FAIL_RUNTIME**. The worker sends **ERROR** and then intentionally throws **IOException** or **IllegalStateException**; try-with-resources still closes the socket.
6. The test verifies 8 accepts, ≥2 overlapping handlers, 6 successful executions, 2 recorded failures, 8 accepted sockets closed, and active=0.
7. The test shuts down the client executor, server listener, acceptor thread, and worker pool, then checks termination state.

The demo protocol is simply **one UTF-8 line per request/response**. Test data is finite and fixed. If using a line-based protocol for untrusted traffic, a real server needs **line length limits**, authentication, TLS, and additional resource controls.

### File TcpConcurrentCleanupDemo.java

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class TcpConcurrentCleanupDemo {
    private static final int CLIENTS = 8;
    private static final int WORKERS = 4;

    static final class Server implements AutoCloseable {
        final ServerSocket listener;
        final Thread acceptor;
        final ThreadPoolExecutor pool = new ThreadPoolExecutor(
                WORKERS, WORKERS, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(CLIENTS),
                new ThreadPoolExecutor.AbortPolicy());

        final CountDownLatch twoActive = new CountDownLatch(2);
        final CountDownLatch letHandlersRun = new CountDownLatch(1);
        final CountDownLatch handled = new CountDownLatch(CLIENTS);

        final AtomicInteger accepted = new AtomicInteger();
        final AtomicInteger active = new AtomicInteger();
        final AtomicInteger peak = new AtomicInteger();
        final AtomicInteger ok = new AtomicInteger();
        final AtomicInteger failed = new AtomicInteger();
        final AtomicInteger closed = new AtomicInteger();
        volatile Throwable acceptFailure;

        Server() throws IOException {
            listener = new ServerSocket(
                    0, 50, InetAddress.getLoopbackAddress());
            acceptor = new Thread(this::acceptLoop, "tcp-acceptor");
            acceptor.start();
        }

        void acceptLoop() {
            try {
                for (int i = 0; i < CLIENTS; i++) {
                    Socket peer = listener.accept();
                    accepted.incrementAndGet();
                    try {
                        pool.execute(() -> handle(peer));
                    } catch (RejectedExecutionException ex) {
                        try {
                            peer.close();
                        } catch (IOException ignored) {
                            // Best-effort close in an already-failing branch.
                        }
                        acceptFailure = ex;
                        handled.countDown();
                    }
                }
            } catch (IOException ex) {
                if (!listener.isClosed()) {
                    acceptFailure = ex;
                }
            }
        }

        void handle(Socket socket) {
            int now = active.incrementAndGet();
            peak.accumulateAndGet(now, Math::max);
            twoActive.countDown();

            try (socket) {
                socket.setSoTimeout(10000);
                if (!letHandlersRun.await(10, TimeUnit.SECONDS)) {
                    throw new IOException("start barrier timeout");
                }

                BufferedReader in = new BufferedReader(
                        new InputStreamReader(
                                socket.getInputStream(),
                                StandardCharsets.UTF_8));
                BufferedWriter out = new BufferedWriter(
                        new OutputStreamWriter(
                                socket.getOutputStream(),
                                StandardCharsets.UTF_8));

                String command = in.readLine();
                if (command == null) {
                    throw new EOFException("empty request");
                }

                if ("FAIL_IO".equals(command) ||
                        "FAIL_RUNTIME".equals(command)) {
                    out.write("ERROR");
                    out.newLine();
                    out.flush();

                    if ("FAIL_IO".equals(command)) {
                        throw new IOException("injected failure");
                    }
                    throw new IllegalStateException(
                            "injected runtime failure");
                }

                out.write("ACK:" + command);
                out.newLine();
                out.flush();
                ok.incrementAndGet();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                failed.incrementAndGet();
            } catch (IOException | RuntimeException ex) {
                failed.incrementAndGet();
            } finally {
                if (socket.isClosed()) {
                    closed.incrementAndGet();
                }
                active.decrementAndGet();
                handled.countDown();
            }
        }

        @Override
        public void close() throws Exception {
            letHandlersRun.countDown();
            listener.close();
            acceptor.join(5000);

            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "worker pool did not terminate");
                }
            }
            if (acceptor.isAlive()) {
                throw new IllegalStateException("acceptor did not stop");
            }
        }
    }

    static String send(int port, String command) throws IOException {
        try (Socket s = new Socket()) {
            s.connect(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), port), 3000);
            s.setSoTimeout(10000);

            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            s.getOutputStream(), StandardCharsets.UTF_8));
            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            s.getInputStream(), StandardCharsets.UTF_8));

            out.write(command);
            out.newLine();
            out.flush();
            return in.readLine();
        }
    }

    static void require(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    public static void main(String[] args) throws Exception {
        Server server = new Server();
        ExecutorService clients = Executors.newFixedThreadPool(CLIENTS);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<String>> replies = new ArrayList<>();

        try {
            for (int i = 0; i < CLIENTS; i++) {
                final int number = i;
                replies.add(clients.submit(() -> {
                    start.await();
                    String command = number == 0 ? "FAIL_IO"
                            : number == 1 ? "FAIL_RUNTIME" : "C" + number;
                    return send(server.listener.getLocalPort(), command);
                }));
            }

            start.countDown();
            require(server.twoActive.await(10, TimeUnit.SECONDS),
                    "fewer than 2 handlers started");
            server.letHandlersRun.countDown();

            for (int i = 0; i < CLIENTS; i++) {
                String expected = i < 2 ? "ERROR" : "ACK:C" + i;
                String actual = replies.get(i).get(10, TimeUnit.SECONDS);
                require(Objects.equals(expected, actual),
                        "wrong response for client " + i);
            }

            require(server.handled.await(10, TimeUnit.SECONDS),
                    "some handlers did not finish");
            require(server.acceptFailure == null,
                    "accept or submit failed");
            require(server.accepted.get() == CLIENTS,
                    "wrong accept count");
            require(server.peak.get() >= 2,
                    "no overlapping handlers");
            require(server.ok.get() == 6, "wrong success count");
            require(server.failed.get() == 2, "wrong failure count");
            require(server.closed.get() == CLIENTS,
                    "accepted socket was not closed");
            require(server.active.get() == 0,
                    "handler remains active");
        } finally {
            start.countDown();
            server.letHandlersRun.countDown();
            clients.shutdownNow();
            try {
                require(clients.awaitTermination(5, TimeUnit.SECONDS),
                        "client pool did not terminate");
            } finally {
                server.close();
            }
        }

        require(server.pool.isTerminated(),
                "worker pool still running");
        require(server.listener.isClosed(), "listener still open");
        require(!server.acceptor.isAlive(),
                "accept thread still running");

        System.out.println("PASS: 8 connections accepted");
        System.out.println("PASS: at least 2 handlers overlapped");
        System.out.println("PASS: 6 successes, 2 injected failures");
        System.out.println("PASS: 8 accepted sockets closed, 0 active");
        System.out.println("PASS: client and worker pools terminated");
    }
}
~~~

### Compile, Run, Expected Output

Create a single file **TcpConcurrentCleanupDemo.java**. Requires **JDK 17 or higher**:

~~~bash
javac --release 17 -encoding UTF-8 TcpConcurrentCleanupDemo.java
java TcpConcurrentCleanupDemo
~~~

**Stdout of a successful run** (logic verified by the Java runtime):

~~~text
PASS: 8 connections accepted
PASS: at least 2 handlers overlapped
PASS: 6 successes, 2 injected failures
PASS: 8 accepted sockets closed, 0 active
PASS: client and worker pools terminated
~~~

The **accept**, **processing start**, and **completion** orders of individual clients are non-deterministic; the program does not print scheduler-dependent ordering. It prints conclusions after checking the **invariants**, so on success stdout is deterministic. If an assertion fails, a Future encounters an error, or a deadline expires, the program throws an exception and **does not print false PASS results**.

### Why Does This Test Truly Verify Concurrency?

Each worker increments **active** and then decrements the **twoActive** latch before waiting on **letHandlersRun**. The test only opens the processing latch after observing at least two handlers. During this window, two handlers are simultaneously present and have not left the processing region; therefore **peakActive ≥ 2** does not rely merely on starting eight clients together.

The Futures are stored **by client index**; the test compares **ACK:C2** against client C2, not against whichever response arrived first. This avoids network/CPU ordering dependencies when testing multiple connections.

### Why Do the Two Failing Requests Still Clean Up Their Sockets?

The handler uses **try (socket)**. After sending ERROR and flushing, the FAIL_IO branch throws **IOException**; the FAIL_RUNTIME branch throws **IllegalStateException**. The catch blocks record failed, while the close operation happens upon exiting try-with-resources **before** finally marks closed and decrements active. Other workers continue serving successful requests.

In production, instead of being silent in catch like this fixture, log and record metrics with a request ID, and decide on the response/retry policy. The counters in the fixture are only used to prove the failure path executed without cluttering stdout.

### Intentional Limitations of the Fixture

The server accepts **exactly eight connections** and then exits the accept loop for testing purposes, rather than being designed as a continuously running server. The worker queue has a limit of 8 tasks, so this scenario **does not intentionally fill the queue** to test overload; overload needs a separate test. **Socket.isClosed()** is evidence of local socket closure, not proof that the kernel TIME_WAIT state ended immediately. The test uses short fixed inputs; production code needs message size limits and full protocol handling.

## 5. Building a Complete Test Matrix

A single important integration test does not replace all real-world failure cases. Cases to add:

| Test Case | How to Create the Scenario | What to Verify |
| --- | --- | --- |
| **Burst of valid clients** | N clients start synchronously | Responses match by ID, no data mixing, active returns to 0 |
| **True parallelism** | Two or more handlers wait on a latch | peakActive ≥ 2 while the latch is still closed |
| **IOException in handler** | Inject exception after accepting socket | Socket closed, failed increments accurately, other clients still work |
| **RuntimeException** | Inject business logic error | Socket still closes, worker pool can still process new requests |
| **Client disconnects early** | Close or shutdownOutput mid-message | Server handles EOF per framing, does not hang |
| **Slow client** | Send partial data then keep socket open | Read timeout/deadline triggers, cleanup occurs |
| **Oversized message** | Send large length or overly long line | Server rejects/aborts safely, no heap exhaustion |
| **Rejected task** | Hold workers, fill bounded queue, submit more | Socket not yet owned by a worker is closed; rejection is recorded |
| **Shutdown while accept is waiting** | Close listener when no new client arrives | Acceptor exits, thread terminates |
| **Shutdown while request is running** | Stop server while workers are blocked | Drain/cancel policy applied, sockets/workers are released |
| **100 start/stop cycles** | Create/close server on port 0 each iteration | No unbounded growth in threads, FDs, or handles |
| **Sustained load** | Run N clients across multiple waves | Peak concurrency bounded, no unbounded backlog growth, latency stable within target |

In tests using JUnit 5, you can place the server fixture in **@BeforeEach** and cleanup in **@AfterEach** (or the test's own try/finally), splitting each case into a separate test with its own assertions. For example, one test only verifies failure isolation, one verifies shutdown with a deadline, and one puts heavy pressure on the bounded queue.

**Do not use one error type to simulate all errors.** A client actively closing a socket differs from a server parse exception; queue rejection differs from read timeout; shutdown differs from successful request processing.

## 6. Controlling State During Server Shutdown

### Closing the Listener Is Not Enough

**ServerSocket.close()** stops listening and causes a blocking accept() to exit per contract, but it **does not automatically close every Socket that was previously accepted**. Handlers must close the sockets they own; during an emergency shutdown, the server may need to track and close active sockets to wake blocked workers.

An orderly shutdown typically consists of:

1. Stop accepting new connections: transition server state, close the listener.
2. Wait for the acceptor thread to stop using join with a deadline.
3. Stop accepting new tasks; decide how to handle queued tasks according to policy.
4. Wait for in-flight workers to complete within a deadline.
5. When the deadline expires, request cancellation/interruption and **close any still-blocked sockets** if needed.
6. Verify the executor is terminated, active is 0, and no resources remain held by the server.

### Shutting Down the Executor in Java 17

**Java 17's ExecutorService must be cleaned up with shutdown/awaitTermination**, not by using try-with-resources as if it were AutoCloseable on every JDK version.

~~~java
// Illustration, placed inside the server lifecycle.
pool.shutdown();
if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
    pool.shutdownNow();
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        throw new IllegalStateException("Pool did not terminate");
    }
}
~~~

**shutdownNow() does not kill threads immediately.** It attempts to interrupt running tasks and returns the list of queued tasks that have not started; code blocked on traditional Socket I/O may need **a socket timeout or an explicit socket close** to exit. For each canceled queued task, you must also account for **which socket it holds** to avoid leaks.

In the fixture, requests complete normally or via injection before shutdown; this is why the test can verify that the worker pool has terminated. Shutdown scenarios when workers are actually blocked require separate tests with active socket tracking.

### Read Timeout Differs from Total Request Timeout

**socket.setSoTimeout(10000)** limits the wait time of each blocking read call, not the total deadline from accept until the response completes. A client could send one byte every few seconds, causing individual reads never to time out while the request drags on indefinitely.

When serving untrusted traffic, combine:

- Frame/line size limits and total byte limits.
- Total request time deadline.
- Read timeout; connect timeout on the client side.
- Active connection limits and a bounded queue.
- Cancellation/closure policy on overload or shutdown.
- Observability to detect clients that hold slots without completing.

## 7. Measuring Resource Leaks and Analyzing Failures

**Inside the JVM:** track active, accepted, closed, queued, failed, thread count, and heap after multiple runs. For stuck threads, use thread dumps or Java Flight Recorder when appropriate.

**At the OS level:** monitor file descriptor/handle counts, **ESTABLISHED** and **CLOSE_WAIT** sockets, thread counts, and changes across multiple open/close cycles. For example:

~~~bash
# Linux: observe TCP states.
ss -tan

# Linux/macOS: process resources (replace example PID with actual PID).
lsof -p 12345
~~~

~~~powershell
# Windows: TCP connections.
Get-NetTCPConnection

# Windows: Java processes and current handle counts.
Get-Process java | Select-Object Id, ProcessName, HandleCount
~~~

**TIME_WAIT is not automatically a leak.** It can be a normal TCP state after closing a connection. Distinguish socket objects/FDs still held by the application from TCP states maintained by the kernel during the protocol lifecycle. Many connections lingering in **CLOSE_WAIT** are especially worth investigating: the peer has closed its send side, but the local application has not finished closing the socket.

Measure **before load, during load, and after load subsides**, then compare across multiple cycles. A single measurement can be affected by GC, thread retention policies, the OS, and other processes.

## 8. Common Design and Testing Mistakes

**Mistake 1: Sending many requests sequentially.** A large number of successful requests does not prove concurrency. You must assert overlap and per-ID response matching.

**Mistake 2: Sleeping a few milliseconds to "ensure" threads run together.** Scheduling is non-deterministic and easily causes flaky tests. Use CountDownLatch and Future with timeouts.

**Mistake 3: Handing the Socket to a worker and immediately closing it in the accept loop.** The worker may use an already-closed Socket. After successful submission, ownership belongs to the worker.

**Mistake 4: Forgetting to close the Socket when execute() is rejected.** The accepted connection has no worker to handle it, risking an FD/handle leak. Catch RejectedExecutionException and close it on the side that still owns the Socket.

**Mistake 5: Catching IOException but ignoring RuntimeException.** Unexpected processing errors can still occur. Putting the Socket in try-with-resources and updating state in finally ensures consistent cleanup.

**Mistake 6: Using a thread pool with an unbounded queue for a high-load server.** A spike in requests can accumulate memory and increase latency; choose a bounded queue and an overload policy.

**Mistake 7: Closing only ServerSocket on shutdown.** Accepted sockets and the worker pool have their own lifecycles; closing the listener does not automatically release accepted sockets.

**Mistake 8: Calling shutdownNow and assuming blocking I/O has stopped.** Interrupts may not be enough; you need socket timeouts/closes and to observe termination.

**Mistake 9: Not setting a timeout on Future.get().** If a handler gets stuck, the entire test can hang indefinitely. Use timeouts and always release latches/pools in finally.

**Mistake 10: Incrementing closed before calling close.** The counter then only counts the intent to clean up, not the actual post-cleanup state.

**Mistake 11: Treating Socket.isClosed() as proof the peer received the response.** Application-level responses/acknowledgments and retry controls are needed if the operation has side effects.

**Mistake 12: Using fixed ports in tests.** Multiple CI jobs can contend for the port; bind port 0 and retrieve the actual port value.

## 9. Self-Check Questions

**Question 1.** Does starting eight clients almost simultaneously guarantee eight handlers run at the same time?  
**Answer:** No. Worker count, queue, and scheduling determine that. You must measure active/peakActive or use a latch to prove overlap.

**Question 2.** A handler throws IllegalStateException while holding a Socket. Who is responsible for closing it?  
**Answer:** The worker that received ownership of the Socket, usually closing it via try-with-resources. Do not expect the accept loop to still hold the Socket.

**Question 3.** The server just accepted a connection, but the pool rejects the task. What is the first action to prevent a leak?  
**Answer:** The side currently holding the Socket must close it, then record the rejection and apply the overload policy.

**Question 4.** Does closing the listener terminate all currently running connections?  
**Answer:** No. ServerSocket is the listening socket; each accepted Socket requires its own owner to handle cleanup.

**Question 5.** Do the two failing requests FAIL_IO and FAIL_RUNTIME force the other six requests to fail?  
**Answer:** No. The fixture proves that an exception in one handler is isolated, that handler's socket is closed, and other clients still receive the correct ACK.

**Question 6.** Why is seeing TIME_WAIT after a test not enough to conclude a leak?  
**Answer:** TCP can legitimately keep the TIME_WAIT state after the Java socket is closed. You need to check FDs/handles, CLOSE_WAIT, active count, and multiple test cycles.

**Question 7.** Does setSoTimeout(10_000) guarantee the entire request finishes within ten seconds?  
**Answer:** No. It limits each individual blocking read operation, not the total request if data continues arriving slowly.

**Question 8.** What keeps the test from hanging if an assertion fails while two handlers are waiting?  
**Answer:** The finally block counts down the latches to open the barriers, shuts down the client executor, and closes the server with appropriate deadlines.

## Conclusion

Testing a multi-connection TCP server requires **proving handlers actually overlap**, matching responses per client, and ensuring one connection's failure does not affect independent connections. Testing cleanup requires **clear Socket/ExecutorService ownership**, closing in all success/error/rejection/shutdown paths, along with measurable invariants such as **active = 0**, closed socket count, and executor terminated state.

A reliable test uses **latches instead of sleep**, **ephemeral ports instead of fixed ports**, **timeouts instead of indefinite waits**, **failure injection instead of guessing network errors**, and **finally to clean up resources even when the test itself fails**.

### References

- [Java 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): accept(), bind(), close().
- [Java 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): socket I/O, close(), and read timeout.
- [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown(), shutdownNow(), awaitTermination().
- [Java 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): bounded pool, queue, and RejectedExecutionException.
- [Java 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): execution synchronization and overlap verification.
- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): per-client results and deadlines.
- [Java 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): thread-safe counters.
