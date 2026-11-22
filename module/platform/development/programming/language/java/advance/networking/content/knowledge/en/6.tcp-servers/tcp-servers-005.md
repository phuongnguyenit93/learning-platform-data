# Sequential Processing Model and the Impact of a Slow Client in a Java TCP Server

A simple TCP server can use exactly **one processing thread**: calling `ServerSocket.accept()`, receiving a `Socket`, handling the entire request and response, closing the socket, and only then returning to `accept()` for the next client. This approach is easy to understand and suitable for introductory exercises, but it has a major consequence: **it only takes one slow client for all subsequent clients to have to wait**, even if they have already established a TCP connection and sent all their data.

This is the phenomenon of **head-of-line blocking at the application processing layer**: a task at the head of the queue holds the processing thread, preventing ready tasks behind it from being served. This lesson clarifies the execution flow, the role of the connection queue and operating system buffers, how to reproduce the issue with Java 17+, options for limiting time/resources, and alternatives for increasing concurrent serving capacity.

## 1. How Does a Sequential Server Work?

Consider the basic structure of a TCP server:

~~~java
// Illustrative snippet inside a method; listener has already been initialized.
// handleClient(socket) reads the request and sends the response until complete.
while (running) {
    Socket client = listener.accept();
    try (client) {
        handleClient(client);
    }
}
~~~

This is the **accept → handle → close → next accept** order on the same thread. If `handleClient` blocks on `InputStream.read()`, `BufferedReader.readLine()`, `OutputStream.write()`, or long CPU processing, the loop cannot advance to the next `accept()` call.

~~~text
                 One application processing thread
                             |
ServerSocket.accept() -------+-----> accepts client A
                             |
                       handles client A
                       readLine() waiting...
                             |
                   [A has not finished]
                             |
                    does not call accept()
                    does not handle B, C...
                             |
                A finishes / timeout / error
                             |
                    closes socket A
                             |
                    accept() client B
                             |
                       handles client B
~~~

Importantly, **TCP can establish a connection in the kernel before the Java application calls `accept()`**. Therefore, client B can complete `connect()`, and even send bytes into the TCP buffer, while the Java server is still reading from A. An established connection at the TCP level **does not mean** B's request has been read or processed by the server program.

A sequential server does not necessarily mean "only one TCP connection exists on the machine". It can have one socket currently being processed by the application and other connections waiting to be accepted; the exact count and behavior depend on the operating system, queues, and load.

## 2. Why Does Just One Slow Client Affect the Entire System?

A client is called "slow" when it causes the serving time to drag out, which may be due to the network, application behavior, or an intentional fault:

- **Sending data slowly or not terminating the message:** the client sends a few bytes without sending a newline character, the full payload length, or the delimiter required by the protocol. `readLine()`/`readNBytes(n)` may wait.
- **Keeping the connection open without sending anything:** the server is blocked in `read()`, waiting for a request that has not arrived.
- **Reading the response very slowly:** when the server writes a large response, the socket send buffer may fill up; `write()` can block because the peer is not reading fast enough.
- **Sending a request that requires a lot of processing time:** heavy computation, slow database queries, or hanging external service calls. Even if the client's network is fast, the processing thread is still occupied.
- **Intentionally trickling bytes:** sending one additional byte every interval, keeping the session alive without forming a complete request. This is the "slow client/slowloris" family of scenarios; one should not assume that simply having a read timeout solves everything.

With a sequential structure, each of the cases above can hold the head position and create wait time for other requests.

### Timeline Example

Suppose the server processes one client at a time:

| Illustrative Time | Client A | Client B | Server |
| --- | --- | --- | --- |
| 0 ms | Connects, sends `HEL` | Not yet arrived | `accept(A)` and `readLine(A)` |
| 100 ms | Has not sent `\\n` | Connects, sends complete `PING\\n` | Still waiting for a complete line from A |
| 1,000 ms | Sends nothing more | Waiting for response | Has not processed B even though B's request has arrived in the buffer |
| 5,000 ms | Sends the remaining part and newline | Still waiting | Finishes reading A, replies to A, then calls `accept(B)` |
| Afterward | Completes | Receives response | Processes B |

The timestamps are only an **illustrative scenario**, not guaranteed latencies. The core point is that **B cannot be processed by the sequential loop before processing A finishes**.

If clients sequentially take serving times `T₁, T₂, ...`, the wait time before the server starts processing the `k`-th client is approximately the sum of the serving times of the preceding clients in the queue (plus overhead), when there is no parallel processing. With a single thread, serving throughput under steady load is limited by the completion rate of one session at a time; a slow client increases both wait time and tail latency variance.

## 3. The Role of `ServerSocket.accept()` and the Backlog Queue

When creating a listener:

~~~java
ServerSocket server = new ServerSocket(8080, 50);
~~~

The value `50` is a **backlog hint** for the connection queue mechanism, not the number of clients Java can process concurrently, and also not a guarantee that exactly 50 connections will be allowed on every OS. The operating system may adjust or cap it according to its policy.

There are three stages to distinguish:

1. **TCP handshake** is handled by the kernel. Upon success, the client may see `Socket.connect()` complete.
2. **The server application calls `accept()`** to retrieve a connected socket from the pending accept queue.
3. **The application actually reads, processes, and writes the response** on the accepted socket.

In the sequential model, step 3 for A must finish before the loop executes step 2 for B. The backlog only helps the kernel hold connections that have not yet been accepted by the application within infrastructure limits. **Increasing the backlog does not increase the number of clients processed at the same time.**

When the server is held up for too long and new connections keep arriving, the queue may fill up. New clients may experience slow connections, timeouts, or rejections depending on the network/OS context. Do not assert that one specific exception always occurs, because TCP backlog behavior and network policies can differ.

## 4. Distinguishing "Slow in accept", "Slow in read", and "Slow in write"

| Blocking Point | Why Does It Wait? | Consequence in a Sequential Loop | Solutions to Consider |
| --- | --- | --- | --- |
| `ServerSocket.accept()` | No new connection to retrieve | The thread is waiting for a new client; no client is currently held by `handleClient` | Configure accept timeout when lifecycle management is needed |
| `Socket.getInputStream().read()` | No bytes or EOF yet | The current client occupies the thread; other clients are not processed | Read timeout, framing, maximum length, overall deadline |
| `BufferedReader.readLine()` | Has not encountered newline or EOF | An unterminated line can hold the thread | Specify delimiter + length/time limits |
| `InputStream.readNBytes(n)` | Fewer than n bytes and no EOF yet | An incomplete request prolongs processing | Limit n, validate length, timeout/deadline |
| `OutputStream.write(...)` | Send buffer may be full, peer reads slowly | Server blocks while sending response; subsequent clients wait | Limit response size, appropriate I/O, and application-level deadline |
| CPU/DB/API processing | Long-running or hung work | Even with a fast socket, a queue builds up | Limit processing time, offload heavy tasks, controlled concurrency |

**Do not confuse timeouts:** `ServerSocket.setSoTimeout(ms)` limits waiting in `accept()`, whereas `Socket.setSoTimeout(ms)` limits **blocking reads** on the socket. Neither sets a deadline for the entire request, and `Socket.setSoTimeout` is not a write timeout.

## 5. Java 17+ Experiment: Two Clients, One Server Thread

This is a standalone program that runs on loopback and **requires no Internet or external DNS**. A single server thread processes two clients sequentially. The slow client sends `SLOW` without a newline. The fast client connects afterward, sends a complete `FAST\\n`, but cannot receive a response until the slow client finishes.

Create the file **`SequentialProof.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SequentialProof {
    private static void handle(Socket socket, List<String> order)
            throws IOException {
        socket.setSoTimeout(5_000);
        BufferedReader in = new BufferedReader(new InputStreamReader(
                socket.getInputStream(), StandardCharsets.UTF_8));
        BufferedWriter out = new BufferedWriter(new OutputStreamWriter(
                socket.getOutputStream(), StandardCharsets.UTF_8));

        String line = in.readLine(); // Wait for newline or EOF.
        if (line == null) {
            throw new EOFException("Empty request");
        }
        order.add(line);
        out.write("ACK:" + line);
        out.newLine();
        out.flush();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        ExecutorService oneServerThread =
                Executors.newSingleThreadExecutor();

        try (ServerSocket server = new ServerSocket(0, 50, loopback)) {
            server.setSoTimeout(5_000);
            CountDownLatch firstAccepted = new CountDownLatch(1);

            Future<List<String>> order = oneServerThread.submit(() -> {
                List<String> result = new ArrayList<>();

                // Accept and process the first client until completion.
                try (Socket first = server.accept()) {
                    firstAccepted.countDown();
                    handle(first, result);
                }

                // Only afterward accept and process the second client.
                try (Socket second = server.accept()) {
                    handle(second, result);
                }
                return result;
            });

            try (Socket slow = new Socket(
                    loopback, server.getLocalPort())) {
                slow.setSoTimeout(5_000);

                if (!firstAccepted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "First client was not accepted");
                }

                BufferedWriter slowOut = new BufferedWriter(
                        new OutputStreamWriter(
                                slow.getOutputStream(),
                                StandardCharsets.UTF_8));
                BufferedReader slowIn = new BufferedReader(
                        new InputStreamReader(
                                slow.getInputStream(),
                                StandardCharsets.UTF_8));

                // Intentionally omit the delimiter so server readLine() waits.
                slowOut.write("SLOW");
                slowOut.flush();

                try (Socket fast = new Socket(
                        loopback, server.getLocalPort())) {
                    fast.setSoTimeout(250);

                    BufferedWriter fastOut = new BufferedWriter(
                            new OutputStreamWriter(
                                    fast.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedReader fastIn = new BufferedReader(
                            new InputStreamReader(
                                    fast.getInputStream(),
                                    StandardCharsets.UTF_8));

                    fastOut.write("FAST");
                    fastOut.newLine();
                    fastOut.flush();

                    try {
                        System.out.println(
                                "fastBeforeSlowFinished="
                                        + fastIn.readLine());
                    } catch (SocketTimeoutException expected) {
                        System.out.println(
                                "fastBeforeSlowFinished=TIMEOUT");
                    }

                    // Unblock the slow client so the server finishes processing A.
                    slowOut.newLine();
                    slowOut.flush();

                    System.out.println(
                            "slowReply=" + slowIn.readLine());

                    // The 250 ms timeout did not close the fast connection.
                    fast.setSoTimeout(5_000);
                    System.out.println(
                            "fastReply=" + fastIn.readLine());

                    System.out.println(
                            "serverOrder="
                                    + order.get(5, TimeUnit.SECONDS));
                }
            }
        } finally {
            oneServerThread.shutdownNow();
        }
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac SequentialProof.java
java SequentialProof
~~~

Verified output on Java (normal loopback environment):

~~~text
fastBeforeSlowFinished=TIMEOUT
slowReply=ACK:SLOW
fastReply=ACK:FAST
serverOrder=[SLOW, FAST]
~~~

**Meaning of each line:**

1. `fastBeforeSlowFinished=TIMEOUT`: the fast client connected/sent the request and called to read the response, but the server was still waiting for the slow client's newline. The timeout here is **the fast client's read timeout**, not proof that the server or fast's TCP connection closed.
2. `slowReply=ACK:SLOW`: when main sends the missing newline for slow, the server completes `readLine()`, replies, and closes the slow socket.
3. `fastReply=ACK:FAST`: after handling slow, the server calls `accept()` a second time, reads FAST, and sends the reply; fast's existing connection from earlier still works.
4. `serverOrder=[SLOW, FAST]`: the server's actual processing order is sequential, even though FAST was ready before SLOW finished.

In the example, `Executors.newSingleThreadExecutor()` provides only **one thread to run the server loop** concurrently with the main thread simulating two clients. It does not make processing the two sockets parallel. `CountDownLatch` eliminates relying solely on `Thread.sleep()` to determine which client is accepted first. Port `0` lets the OS assign a free port on loopback. The 5-second timeouts bound how long the test environment can get stuck; on an overloaded machine or one where opening sockets is blocked, the program may throw an exception instead of printing the exact example output.

**Note on `readLine()`:** this method reads a line when it encounters LF, CR, CRLF, or EOF; if the peer closes its output without sending a newline, `readLine()` can return the remaining characters. In the demo, slow intentionally **keeps its output open** until it sends the newline, to create a clear waiting state. Do not confuse "no newline" with "guaranteed to wait indefinitely even after EOF".

## 6. What Do Timeouts Help With and What Is Still Missing?

A first measure is configuring a timeout so that one client cannot hold the thread **indefinitely in a single blocking call**:

~~~java
// Illustrative fragment inside handleClient(Socket client).
client.setSoTimeout(2_000); // 2 seconds per blocking read.
BufferedReader reader = new BufferedReader(
        new InputStreamReader(client.getInputStream(),
                StandardCharsets.UTF_8));
try {
    String line = reader.readLine();
    if (line == null) {
        // Peer closed the sending side before sending a request.
        return;
    }
    // Process a valid line (length/framing checks needed).
} catch (SocketTimeoutException timeout) {
    // Proactively terminate the session per server policy.
    // try-with-resources in the caller will close the socket.
}
~~~

This is a **fragment** inside a method that is allowed to `return` and is called with a connected socket; it is not a standalone complete Java program. A `SocketTimeoutException` indicates that the read operation did not receive enough data within the wait interval, **and does not automatically prove the peer disconnected**. If you decide to close the socket on timeout, that is the server's policy.

Three types of deadlines must be distinguished:

- **Read idle timeout:** `Socket.setSoTimeout` limits the wait time during blocking reads at the socket layer. When a client occasionally sends more data, `readLine` can keep receiving bytes and waiting for the end of the line. An idle timeout alone does not guarantee that total session time stays below a threshold.
- **Overall request deadline:** sets the latest time by which the request must be completely received and processed. For example, a request must be complete within 5 seconds from when serving begins, regardless of whether bytes are trickled one by one. You need to measure elapsed time and cancel/close when exceeded.
- **Processing / response deadline:** limits CPU work, DB/API calls, and the response-writing phase. `setSoTimeout` **does not** apply to `OutputStream.write` or all server operations. An application-level deadline or non-blocking I/O may be required.

**Enforcing a request length limit is mandatory:** a client sending an infinitely long line without a newline can cause `BufferedReader.readLine()` to accumulate data in memory. When using a line-based protocol, you must check the maximum number of characters/bytes, accept or reject newlines according to rules, and set an overall deadline. If using length-prefixed frames, you must validate the length before allocating memory and verify that the body has enough bytes.

Deadlines only **limit the harm of each individual client**, but a sequential server still serves one client at a time; when there are many slow clients, the cumulative wait time remains large.

## 7. Nature of Head-of-Line Blocking and Scope of Impact

Do not conflate three phenomena:

| Phenomenon | At Which Layer? | Example |
| --- | --- | --- |
| Head-of-line due to a **sequential server** | Application processing thread | Server is in `readLine(A)` so it cannot process B |
| Head-of-line due to a **single TCP byte stream** | Reliable byte ordering within the same connection | Losing an earlier segment can make the application wait for earlier bytes even if later data has arrived |
| Backlog / scheduling queue | Kernel, scheduler, pool | TCP connection waiting for the application to accept or waiting for a free worker |

This lesson focuses on **the first type**. Adding more TCP connections does not fix a Java thread that only handles one connection at a time. Conversely, increasing the number of workers does not change the byte-ordering nature of a single TCP stream.

Beyond serving capacity, there are two more consequences:

- **Fairness and tail latency:** a fast request behind a slow request can experience latency disproportionate to its own processing time. A fast client's average does not help if it frequently has to queue behind very long clients.
- **Queue/resource exhaustion:** waiting connections consume sockets, file descriptors, and kernel memory; when queues/pools fill up, the system may reject or delay new connections. Do not use "increase the backlog" as the sole solution for a blocked endpoint.

## 8. Ways to Organize a Server to Reduce the Impact

### 8.1. One Dedicated Worker per Client

An intuitive pattern is for the accept thread to quickly hand off the socket to a worker:

~~~java
// Illustrative fragment inside a method that has ServerSocket server.
// handleClient(client) must itself limit time and request size.
while (running) {
    Socket client = server.accept();
    Thread worker = new Thread(() -> {
        try (client) {
            handleClient(client);
        } catch (IOException ex) {
            logClientFailure(ex);
        }
    });
    worker.start();
}
~~~

When A is slow, A's worker is held, but B's worker still has a chance to run. However, creating an unbounded platform thread for **every** connection can exhaust memory, CPU scheduling, and file descriptors when thousands of clients connect concurrently. The snippet above illustrates the strategy, **not a complete safe design**.

### 8.2. Bounded Worker Pool and Bounded Queue

With Java 17, you can separate the accept thread from processing threads using `ThreadPoolExecutor`:

~~~java
// Fragment inside a method that has ServerSocket server.
// imports: java.net.Socket, java.util.concurrent.*
// handleClient(Socket) must be provided by the application.
ThreadPoolExecutor workers = new ThreadPoolExecutor(
        4, 4,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(16),
        new ThreadPoolExecutor.AbortPolicy());

try {
    while (!Thread.currentThread().isInterrupted()) {
        Socket client = server.accept();
        try {
            workers.execute(() -> {
                try (client) {
                    client.setSoTimeout(2_000);
                    handleClient(client);
                } catch (Exception ex) {
                    // Log error and apply client termination policy.
                    recordFailure(ex);
                }
            });
        } catch (RejectedExecutionException overloaded) {
            // Pool and queue are full: do not hold the client indefinitely.
            client.close();
        }
    }
} finally {
    workers.shutdown();
}
~~~

This is a **sample implementation fragment**; you need to place it in a class, provide `handleClient` and `recordFailure`, and add listener error handling, loop interruption, and complete shutdown before production use.

In this design:

1. The `accept()` thread hands clients to the pool and can accept the next connection sooner.
2. At most four workers process concurrently; 16 tasks waiting in the queue **are not processed immediately**.
3. If all four workers are busy and the queue is full, `execute()` throws `RejectedExecutionException` under `AbortPolicy`; the application closes the newly accepted socket so resources are not leaked.
4. If slow clients occupy all four workers, other clients can still wait a very long time or be rejected. A pool **reduces system-wide blocking**, but does not eliminate the need for timeouts, admission control, and resource limits.
5. The queue holds open sockets: you must consider timeouts from connection time, limits on pre-processing queue wait time, and cleaning up sockets remaining in the queue on shutdown. A `workers.shutdown()` call alone does not handle every socket-closing or pending-request scenario.

Avoid blindly using `CallerRunsPolicy` in the `accept()` thread: when the pool is full, the accept thread itself will run `handleClient`, inadvertently bringing blocking back into the connection-accepting loop.

### 8.3. Non-Blocking I/O with `Selector`

Java NIO provides `ServerSocketChannel`, `SocketChannel`, and `Selector` so that one or a group of event loops can monitor many connections ready for reading/writing. When client A has no data, the event loop can handle client B instead of waiting on A's blocking read.

This approach requires state machines, per-client buffers, handling partial reads/writes, framing, `OP_READ`/`OP_WRITE` events, and backpressure. If a callback in the event loop performs long CPU/DB work, it **can still block** other connections; blocking work should be offloaded to an appropriate worker.

### 8.4. Virtual Threads on Java 21+

With Java 21+, virtual threads allow keeping readable blocking-style code while serving many more concurrent sessions:

~~~java
// Java 21+ fragment; does not compile on Java 17.
// ServerSocket server and handleClient(Socket) are already provided.
while (running) {
    Socket client = server.accept();
    Thread.startVirtualThread(() -> {
        try (client) {
            handleClient(client);
        } catch (IOException ex) {
            recordFailure(ex);
        }
    });
}
~~~

Virtual threads reduce the thread cost of many I/O-waiting tasks, and **do not** make sockets/heap, DB connections, CPU, or downstream services infinite. You still need to limit the number of connections/requests, lifetimes, input sizes, and resources; avoid holding monitors across long blocking sections in cases that can cause pinning, and test behavior on the actual JDK version.

**Version boundary:** the `SequentialProof.java` example and bounded pool apply to Java 17+; `Thread.startVirtualThread` is a Java 21+ API and must not be used when Java 17 compatibility is required.

## 9. Choosing the Right Model for the Problem

| Model | Advantages | Risks / Costs | When Appropriate |
| --- | --- | --- | --- |
| Sequential, single thread | Easy to learn, little shared state | One slow client holds all subsequent clients; low throughput under blocking I/O | Demos, internal tools with very few clients, tightly controlled protocols |
| Platform thread per client | Isolates I/O waits between clients | Very many threads cause memory/scheduler overhead | Few clients or clearly bounded session count |
| Fixed/limited worker pool | Controls thread/task count and has overload policy | Queue wait, load rejection, risk of full-pool saturation | Java 17+ TCP servers needing bounded concurrency |
| NIO selector/event loop | Manages many I/O-waiting connections | Complex state/framing/backpressure; blocking callbacks cause stalls | High connection counts, suitable I/O traffic |
| Virtual thread per connection | Keeps blocking code easy to understand, lighter than platform threads under many I/O waits | Still requires limiting sockets/memory/CPU/downstream resources | Java 21+ with many I/O-waiting clients |

No model completely eliminates slow requests. You must **limit the harm of individual clients and protect shared resources**. If a pool only has four workers and all four are held by four "trickling" requests, stalling behavior still exists even without a single thread.

## 10. Checklist for Observing and Diagnosing a Stalled Server

When client B reports "connected successfully but no response", check in order:

1. **Timestamps:** record timestamps for kernel accept, Java `accept()` return, processing start, full request receipt, and response completion. Separate pre-processing wait time from processing time.
2. **Thread dump:** check whether serving threads are stuck in `SocketInputStream.read`, `BufferedReader.readLine`, `SocketOutputStream.write`, DB queries, or CPU code. Do not jump to blaming the network if the bottleneck is actually the DB.
3. **Framing:** has the client sent the newline, declared length, EOF, or end marker? Does the protocol wait for one side to close output before replying, while the other side is also waiting for a response?
4. **Timeouts and deadlines:** is `setSoTimeout` configured, are there an overall deadline and max request size, and are clients sending one byte at a time to bypass idle timeouts?
5. **Queues and overload:** number of sockets being processed, connections waiting for accept, worker queue depth, active task count, queue time, rejection rate, file descriptor count, and memory.
6. **Resource closing:** are all accepted sockets closed in `try-with-resources` or `finally`? On timeout, abnormal client disconnect, or task rejection, is the connection leaked?
7. **Mitigation:** test a controlled slow client on loopback/staging and observe the response time of a fast client arriving afterward. Compare against using a bounded pool with equivalent deadline/framing settings.

Useful metrics are **wait time until served**, request read time, processing time, response write time, active connection count, timeout rate, and overload rate. Measuring only total latency makes it difficult to determine whether the bottleneck is sequential ordering or per-request processing.

## 11. Common Misconceptions

1. **"Once a client has a successful TCP connection, the Java server is already processing it."** False: the connection may be sitting in the `accept()` queue, or already accepted but still waiting for a worker.
2. **"Increasing the backlog solves slow clients."** False: the backlog manages the queue in the kernel; it does not add application processing threads.
3. **"Only `readLine()` causes blocking."** False: `read()`, `readNBytes()`, `write()`, and DB/CPU work can all prolong a session.
4. **"Setting `Socket.setSoTimeout(2000)` limits the entire request to two seconds."** False: it limits waiting on blocking reads; trickled bytes and post-read processing can still extend total time.
5. **"`ServerSocket.setSoTimeout` handles slow clients."** False: it only limits waiting for **new connections** in `accept()`, not accepted sockets.
6. **"A successful `write()` proves the client has processed the response."** False: data may have only entered the local buffer; application/protocol-level proof is needed if business logic requires it.
7. **"Thread per client can scale indefinitely."** False: threads, sockets, CPU, memory, DB connections, and the scheduler are all finite.
8. **"NIO is always faster for every application."** No such conclusion holds: event loops suit certain workloads, but require non-blocking design and careful buffer/backpressure management.
9. **"With virtual threads, request limits are unnecessary."** False: virtual threads do not bound the number of connections/sockets or downstream system load.
10. **"One slow client immediately drops all other clients' connections."** Not necessarily: many clients may still hold TCP connections while waiting for application processing; under prolonged overload or a full queue, some new connections may be delayed, time out, or be rejected depending on the environment.

## 12. Self-Check

**Question 1.** The server calls `accept(A)`, then `readLine(A)`. A sends `hello` without a newline or FIN. B has called `connect()` successfully and sent `PING\\n`. Why does B not have a response yet?  
**Answer:** The server is processing sequentially and is held in `readLine(A)`; it has not called `accept(B)` or read B's request, even though B's TCP connection may already be established and its data buffered.

**Question 2.** If the backlog is increased from 50 to 500, does the number of requests the server can process concurrently become 500?  
**Answer:** No. Backlog relates to the kernel's connection queue; a sequential server still has only one thread processing requests at a time.

**Question 3.** Does `setSoTimeout(1000)` protect against a client sending one byte every 900 ms with an unbounded request length?  
**Answer:** Not guaranteed. That is a read inactivity timeout; an overall deadline and size/frame limits are also needed.

**Question 4.** In the demo, does `fastBeforeSlowFinished=TIMEOUT` mean fast's TCP connection is dead?  
**Answer:** No. The same fast socket can still receive `ACK:FAST` after the server finishes handling slow; the timeout was the fast client's read wait time.

**Question 5.** When switching to a four-worker pool, can a slow client still affect others?  
**Answer:** Possibly, though it usually occupies only one worker. If all four workers are held or the queue is full, other clients will still wait or be rejected per the overload policy.

**Question 6.** When should NIO selectors or virtual threads be used?  
**Answer:** When you need to manage many I/O-waiting connections concurrently. NIO requires state machines and a non-blocking event loop; virtual threads require Java 21+ and still need resource limits.

## References

- Java SE 17 — `ServerSocket`, `accept()`, `setSoTimeout()`, backlog: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- Java SE 17 — `Socket`, `connect()`, `setSoTimeout()`, and stream I/O: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- Java SE 17 — `BufferedReader.readLine()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html
- Java SE 17 — `ThreadPoolExecutor` and rejection policies: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 17 — `Selector` and NIO: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html
- Java SE 21 — `Thread.startVirtualThread()`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html
