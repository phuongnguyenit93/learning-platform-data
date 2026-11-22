# Separating the Listening Socket from Per-Client Sockets in a TCP Server (Java)

A TCP server typically has **one listening `ServerSocket`** and multiple **`Socket` instances serving connected clients**. They are related through `accept()`, but they are **not the same socket, do not share the same lifecycle, and cannot be closed in place of each other**. Understanding this boundary helps build a TCP server that serves multiple clients without leaking resources or accidentally cutting connections.

For example, the server is listening at `127.0.0.1:9000`. Client A connects, and the server gets a dedicated socket to exchange data with A. Client B connects later, and the server gets another dedicated socket for B. `ServerSocket` continues handling the job of waiting for new connections. **Closing A's socket does not close the listener or B's socket; closing the listener does not automatically close the already accepted A/B sockets.**

This lesson belongs to the **TCP Servers** topic and focuses directly on distinguishing the listening socket from per-client handling sockets, from structure and code to shutdown. The examples use `java.net`, blocking TCP, and Java 17+; no framework or Internet connection is required.

## 1. Objectives

After this lesson, you can:

- Explain the roles of `ServerSocket.bind()` and `ServerSocket.accept()`, as well as the returned `Socket` object.
- Distinguish the listener's local endpoint from the local/remote endpoints of an accepted connection.
- Structure an accept loop that keeps the listener open while each accepted socket has its own scope.
- Choose the right place to use `try-with-resources`, avoiding closing a socket before the worker finishes processing.
- Explain why closing the listener does not close accepted connections and vice versa.
- Separate timeouts/errors at the accept layer from timeouts/errors of each client.
- Design ownership transfer, concurrency limits, and controlled TCP server shutdown.
- Run two standalone Java programs demonstrating the lifecycle relationship between the listener and accepted sockets.

## 2. Diagram: One Listener, Multiple Connections

~~~text
                            TCP SERVER
                     +----------------------+
                     | ServerSocket         |
                     | local :9000          |
                     | accept()             |
                     +----------+-----------+
                                |
                +---------------+---------------+
                |                               |
             accept A                        accept B
                |                               |
         +------+--------+               +------+--------+
         | Socket A      |               | Socket B      |
         | local :9000   |               | local :9000   |
         | remote A:pa   |               | remote B:pb   |
         +------+--------+               +------+--------+
                |                               |
        InputStream/OutputStream       InputStream/OutputStream
                |                               |
             Client A                        Client B

close(Socket A): closes A; listener and B do not close automatically.
close(listener): stops accepting new connections; already accepted A and B
                 are not closed automatically.
~~~

Java objects to distinguish:

| Type | Role | Typical Methods | Lifetime Scope |
| --- | --- | --- | --- |
| `ServerSocket` | Bind/listen on TCP and accept new clients | `bind()`, `accept()`, `getLocalPort()`, `close()` | Server/listener lifecycle |
| Server-side `Socket` from `accept()` | An accepted TCP connection | `getInputStream()`, `getOutputStream()`, `getRemoteSocketAddress()`, `close()` | Single connection lifecycle |
| Client-side `Socket` | The other end of the TCP connection | `connect()`, `getInputStream()`, `getOutputStream()`, `close()` | Client connection lifecycle |

**Important:** `ServerSocket` does not have `getInputStream()` or `getOutputStream()` to read a client's request. Application data must be read/written on the **accepted `Socket`**. Each successful return from `accept()` is a separate connection; the server keeps the listener so it can call `accept()` next time.

## 3. Listening with `ServerSocket`: bind and accept

### 3.1. Initializing the Listener

~~~java
ServerSocket listener = new ServerSocket();
listener.bind(new InetSocketAddress(
        InetAddress.getLoopbackAddress(), 9000), 64);
~~~

This is an **in-method code snippet** (requires `import java.net.ServerSocket;`, `InetSocketAddress`, `InetAddress` and handling/declaring `IOException`). Port 9000 is just an example; binding may fail if the port is already in use.

- `bind()` attaches the listener to a local address/port. With loopback, the demo only exposes the service to programs on the same machine.
- Port `0` asks the operating system to choose an available port; after binding, call `listener.getLocalPort()` to find the actual port.
- `backlog` is a parameter for the pending connection queue waiting to be accepted as supported by the OS. It is **not** a limit on the number of clients served over the server's lifetime, nor is it the thread pool size.
- If binding fails (`BindException` or another `IOException`), the server does not yet have a valid listening endpoint. Configuration/port issues must be handled rather than assuming it is ready.
- Constructors `new ServerSocket(port)` or `new ServerSocket(port, backlog, bindAddr)` can also bind immediately; `new ServerSocket()` + `bind()` helps separate configuration and initialization.

### 3.2. `accept()` Creates a New Connection Endpoint

~~~java
Socket accepted = listener.accept();
~~~

In the blocking model, `accept()` waits until a client establishes a connection or a timeout/error occurs. The return value is a **new `Socket` object** for the accepted connection, not `listener` itself.

While `accepted` is reading/writing data, the listener remains bound if not closed. When more clients need to be served, server code calls `accept()` again. An accept **does not automatically read application data**; TCP has only established the byte stream.

Simple accept loop example:

~~~java
try (ServerSocket listener = new ServerSocket(9000)) {
    while (running) {
        try (Socket accepted = listener.accept()) {
            handleClient(accepted);
        }
    }
}
~~~

This is **illustrative code**, not a standalone program: `running` and `handleClient` are provided by the application; `IOException` must be handled. Because the handler runs **directly on the accept thread**, this server processes clients **sequentially** and does not serve them concurrently. It demonstrates the correct lifecycle, though it is not the only way to handle multiple clients.

### 3.3. Why Do Multiple Accepted Sockets Share the Same Server Port?

Suppose the listener is at `192.0.2.10:9000`; client A is at `198.51.100.11:51001`, B is at `198.51.100.12:51002`:

~~~text
Listener local endpoint: 192.0.2.10:9000

Accepted A:
    local  = 192.0.2.10:9000
    remote = 198.51.100.11:51001

Accepted B:
    local  = 192.0.2.10:9000
    remote = 198.51.100.12:51002
~~~

The IPs above belong to documentation ranges, not live endpoints. TCP distinguishes connections by the 4-tuple `(local IP, local port, remote IP, remote port)`. Accepted sockets can share the same server **local port** while having different remote endpoints, so their byte streams do not mix.

In code:

~~~java
listener.getLocalSocketAddress();  // listener endpoint
accepted.getLocalSocketAddress();  // local endpoint of this connection
accepted.getRemoteSocketAddress(); // corresponding client
accepted.getLocalPort();           // local port, usually equals listener port
accepted.getPort();                // REMOTE port of the client
~~~

This is an **illustrative snippet** with already created variables. Do not mistake `accepted.getPort()` for the listener port: on `Socket`, it is the **remote port**. Do not hard-code dynamic ports in stdout tests because the OS may choose different values across runs.

## 4. Lifecycle and Ownership Are Two Different Levels

A TCP server needs to define resource-closing responsibilities:

1. **The server manager owns the listener**: creates, binds, starts accepting, stops accepting, and closes the `ServerSocket`.
2. **The connection handler owns the accepted socket**: reads requests, writes responses, and closes the corresponding `Socket` when the transaction or session ends.

~~~text
Server scope:
    create/bind listener
    while receiving new clients:
        accepted = listener.accept()
        transfer ownership to handler
    close listener

Per-client handler scope:
    try (accepted) {
        read this client's bytes
        process its protocol
        write reply
    }
    // accepted.close() happens here
~~~

If the code calls `handleClient(accepted)` synchronously, the caller can use `try (Socket accepted = listener.accept())` to close it after the handler. If the accepted socket is handed off to an asynchronous worker, the worker must keep the resource scope inside the handler itself. You must not use a `try (accepted)` in the caller and return immediately after `executor.submit()`.

### 4.1. Premature Socket Closure Bug When Handing Off to an Executor

~~~java
// WRONG if handler has not finished running:
try (Socket accepted = listener.accept()) {
    executor.submit(() -> handleClient(accepted));
} // accepted.close() immediately after submit!
~~~

`submit()` only schedules the work to run. When the caller's `try` block ends, the accepted socket is closed even though the task has not started yet, or is in the middle of reading/writing. `SocketException`, premature EOF, and corrupted responses may appear and be hard to reproduce.

Pattern where ownership is transferred to the worker (illustrative snippet; helper names exist elsewhere):

~~~java
Socket accepted = listener.accept();
try {
    executor.execute(() -> {
        try (accepted) {
            handleClient(accepted);
        } catch (IOException error) {
            logConnectionError(error);
        }
    });
} catch (RejectedExecutionException rejected) {
    try {
        accepted.close();
    } catch (IOException closeError) {
        rejected.addSuppressed(closeError);
    }
    throw rejected;
}
~~~

This snippet requires `Socket`, `IOException`, and `RejectedExecutionException`; `listener`, `executor`, `handleClient`, and `logConnectionError` are declared by the application. Rule: when the task is handed off successfully, the handler owns the socket; when the executor rejects it, the caller **must still close the socket**. Additional runtime exception handling/logging and overload policies may be needed in real production code.

### 4.2. Separating `try-with-resources` by Lifetime

~~~text
try (listener) {             <-- scope lives across multiple accept calls
    accept A
    handler A: try (A) { ... }   <-- closes A when handling A finishes
    accept B
    handler B: try (B) { ... }   <-- closes B independently
}                              <-- listener closes only at end of scope
~~~

Not every connection necessarily has only one request. A protocol may allow multiple consecutive requests over the same TCP connection; the handler keeps the accepted socket for the lifetime of the **connection**, rather than closing it every time it sees one frame if the protocol still needs the socket.

## 5. Closing the Listener Differs from Closing an Accepted Socket

### 5.1. Closing an Accepted Socket

`accepted.close()` ends **that connection**. It closes the streams of the accepted socket and does not close the listening `ServerSocket`, nor does it automatically affect connections B/C. Closing the `InputStream` or `OutputStream` obtained directly from the socket also closes that socket itself, so avoid closing a stream before bidirectional communication has finished.

For a closed socket:

- `accepted.isClosed()` is `true`.
- `accepted.isConnected()` may still be `true` because it records that it was once connected; it is **not** a check of whether the peer is still alive.
- A single `close()` does not guarantee the peer has finished processing the data just written. If business logic requires confirmation, there must be an ACK/response at the application layer.

### 5.2. Closing the Listener

`listener.close()` closes the **listening endpoint**. A thread waiting in `listener.accept()` may be unblocked with a `SocketException` because the listener closed. No further `accept()` calls can be made on a closed listener.

However, **already existing accepted sockets are independent**: the server can let in-flight requests finish after the listener closes. This is an important mechanism for graceful shutdown: stop accepting new connections while continuing to serve existing ones within a given deadline.

If the server also wants to forcefully stop existing clients, it must close the accepted sockets it owns, or ask the handlers to cooperate in canceling. Simply closing the listener **does not release all file descriptors and workers of running connections**.

### 5.3. Action Comparison Table

| Action | Accepts New Connections? | Impact on Accepted Connections |
| --- | --- | --- |
| `acceptedA.close()` | Yes, if listener is still open | Only A is closed; B does not close with it |
| `listener.close()` | No on that listener | Already accepted A/B can continue I/O |
| `acceptedA.shutdownOutput()` | Listener is unaffected | Ends A's **sending direction**; can still read from A |
| `executor.shutdown()` | Depends on accept loop; does not auto-close listener | Already accepted tasks have a chance to finish |
| `executor.shutdownNow()` | Does not auto-close listener | Sends interrupt request; not guaranteed to unblock blocking I/O |
| Exiting `try (listener)` | Listener closes | Accepted sockets need their own lifecycle |

`shutdownOutput()`/`shutdownInput()` is a **one-way half-close** of a `Socket`, not a command to shut down a TCP server. For buffered data, you must flush according to the protocol before half-closing if the full request needs to be sent.

## 6. Accept Loop: Sequential, Thread Pool, and Backpressure

### 6.1. Sequential

~~~text
accept A -> handle A -> close A
accept B -> handle B -> close B
accept C -> handle C -> close C
~~~

Advantages: easy to read, simple, no need to synchronize state across multiple handlers. Drawback: a slow client A can hold the accept thread in `read()`, forcing B/C to wait to be processed, even though the OS may be queuing some connections in the backlog.

### 6.2. Separating the Accept Thread from Workers

~~~text
                  [ServerSocket]
                       |
                    accept()
                       |
           +-----------+------------+
           |           |            |
        Socket A    Socket B      Socket C
           |           |            |
        Worker A    Worker B      Worker C
           |           |            |
        close A     close B       close C

Accept loop continues using the same listener.
~~~

Workers can be platform threads, a thread pool, virtual threads in Java 21+, or an event loop with `java.nio.channels` under another architecture. The goal here is to **separate the work of accepting connections from the work of reading/writing for each client**.

This does not mean every client must have a permanent thread. Concurrency limits are needed:

- A small thread pool can protect the CPU, but an unbounded queue still allows the number of waiting accepted sockets to grow too large.
- A bounded queue and rejection/load-shedding policy must be paired with **closing the newly accepted socket when it cannot be handled**.
- Virtual threads (Java 21+) reduce thread overhead when many operations wait on I/O, but you still must limit file descriptors, RAM, message size, and downstream calls.
- NIO/`Selector` can manage many connections in an event loop, but the accepted channel and listener channel remain two separate roles.

`backlog` is **not** a limit on active accepted sockets, nor does it automatically replace rate limiting or application resource limits.

## 7. Runnable Example 1: One Listener Serving Two Clients

This example binds to loopback and port `0` so the OS picks an available port. One worker calls `accept()` twice, closes the first client's socket, and then continues accepting the second client. Finally, `main` checks the listener's state. Both client and server have timeouts to prevent the demo from hanging indefinitely.

Create file **`TcpTwoClientsDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.EOFException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TcpTwoClientsDemo {
    public static void main(String[] args) throws Exception {
        ServerSocket listener = new ServerSocket();
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try (listener) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0), 16);
            listener.setSoTimeout(5_000);

            Future<Integer> server = workers.submit(() -> {
                int handled = 0;
                for (int i = 0; i < 2; i++) {
                    try (Socket accepted = listener.accept()) {
                        accepted.setSoTimeout(5_000);
                        BufferedReader in = new BufferedReader(
                                new InputStreamReader(
                                        accepted.getInputStream(),
                                        StandardCharsets.UTF_8));
                        BufferedWriter out = new BufferedWriter(
                                new OutputStreamWriter(
                                        accepted.getOutputStream(),
                                        StandardCharsets.UTF_8));
                        String request = in.readLine();
                        if (request == null) {
                            throw new EOFException("Missing request");
                        }
                        out.write("ACK:" + request);
                        out.newLine();
                        out.flush();
                        handled++;
                    }
                }
                return handled;
            });

            for (String request : List.of("one", "two")) {
                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            InetAddress.getLoopbackAddress(),
                            listener.getLocalPort()), 2_000);
                    client.setSoTimeout(5_000);
                    BufferedWriter out = new BufferedWriter(
                            new OutputStreamWriter(client.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedReader in = new BufferedReader(
                            new InputStreamReader(client.getInputStream(),
                                    StandardCharsets.UTF_8));
                    out.write(request);
                    out.newLine();
                    out.flush();
                    String reply = in.readLine();
                    if (reply == null) {
                        throw new EOFException("Missing reply");
                    }
                    System.out.println("Request " + request + " -> " + reply);
                }
            }
            System.out.println("Handled: " + server.get(5, TimeUnit.SECONDS));
            System.out.println("Listener still open: " + !listener.isClosed());
        } finally {
            workers.shutdownNow();
        }
        System.out.println("Listener closed: " + listener.isClosed());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 TcpTwoClientsDemo.java
java TcpTwoClientsDemo
~~~

**Verified stdout with OpenJDK 24:**

~~~text
Request one -> ACK:one
Request two -> ACK:two
Handled: 2
Listener still open: true
Listener closed: true
~~~

Result explanation:

1. `listener.bind(..., 0)` creates **one** server endpoint; `getLocalPort()` returns the assigned port. Both clients connect to this exact port.
2. `workers.submit()` lets the server accept connections in a worker concurrently with the main thread acting as the client; this is a demo design, not an optimal thread pool setup.
3. Each `try (Socket accepted = listener.accept())` owns **one** server-side connection. Finishing request `one` closes the first accepted socket; the listener stays alive long enough to accept `two`.
4. `BufferedReader.readLine()` requires a newline; the client sends `out.newLine()` and `flush()`. When the server replies, it also flushes so the client can read the line.
5. `Future.get()` waits for both connections to be processed and prevents printing conclusions before the worker finishes.
6. `Listener still open: true` appears **before** exiting `try (listener)`. After leaving the scope, `Listener closed: true`.

Because the server handles exactly two iterations, it is not a continuously running service. For a production server, you need a loop with a stop condition, load limits, active socket tracking, and comprehensive error handling.

## 8. Runnable Example 2: Closing the Listener While the Accepted Connection Stays Alive

The second program accepts one client, then the worker **immediately closes the listener**. The accepted socket still reads four bytes `PING`, sends `OK\n`, and the client still receives the response. This is a direct test of the independence of the two socket types.

Create file **`CloseListenerDemo.java`**:

~~~java
import java.io.EOFException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CloseListenerDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket(
                0, 16, InetAddress.getLoopbackAddress())) {
            Future<Boolean> served = worker.submit(() -> {
                try (Socket accepted = listener.accept()) {
                    listener.close();
                    boolean connectionStillOpen = !accepted.isClosed();
                    accepted.setSoTimeout(5_000);
                    byte[] input = accepted.getInputStream().readNBytes(4);
                    if (input.length != 4) {
                        throw new EOFException("Need four bytes");
                    }
                    accepted.getOutputStream().write(
                            "OK\n".getBytes(StandardCharsets.US_ASCII));
                    accepted.getOutputStream().flush();
                    return connectionStillOpen;
                }
            });

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort()), 2_000);
                client.setSoTimeout(5_000);
                client.getOutputStream().write(
                        "PING".getBytes(StandardCharsets.US_ASCII));
                byte[] reply = client.getInputStream().readNBytes(3);
                System.out.print("Reply: " +
                        new String(reply, StandardCharsets.US_ASCII));
            }
            System.out.println("Listener closed: " + listener.isClosed());
            System.out.println("Accepted was open: " +
                    served.get(5, TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CloseListenerDemo.java
java CloseListenerDemo
~~~

**Verified stdout:**

~~~text
Reply: OK
Listener closed: true
Accepted was open: true
~~~

`listener.close()` stops the listening endpoint from accepting new clients. However, `accepted.isClosed()` is still `false` right after closing the listener; the accepted socket's streams still communicate with the client. The client receives `OK`, and then the handler exits `try (accepted)` to close the connection. Therefore, **you must not assume a closed listener means all existing clients have stopped working**.

## 9. Designing Server Shutdown Around Two Lifecycles

A controlled server shutdown should separate **stopping new client acceptance** from **releasing active connections**:

~~~text
RUNNING
  |
  v
STOP_ACCEPTING
  - set stop state
  - listener.close() to unblock blocking accept()
  - do not hand off additional accepted sockets to workers
  |
  v
DRAINING
  - let already running handlers finish within deadline
  - stop accepting new tasks into executor
  - wait with a deadline, do not wait indefinitely
  |
  v
FORCE_CLOSE (if deadline exceeded)
  - close active accepted sockets owned by the server
  - request cancel/interrupt on workers and observe errors
  |
  v
STOPPED
  - close remaining owned resources
  - confirm executor has shut down
~~~

Key points:

- Closing `ServerSocket` typically causes a thread waiting in `accept()` to receive `SocketException`. If the close is a **planned shutdown**, this is an expected signal, not necessarily a fatal error requiring a retry.
- Closing the listener **does not automatically** call `close()` on previously accepted sockets. To force-close, you must track each connection, usually via a thread-safe registry tied to handler ownership.
- `ExecutorService.shutdown()` stops accepting new tasks but does not automatically close accepted sockets. `shutdownNow()` requests an interrupt; it must not be treated as a guarantee to unblock all blocking socket I/O.
- When forced shutdown is required, **closing accepted sockets owned by the application** is often a necessary step to unblock threads stuck in I/O; combine this with timeouts and deadlines.
- A server handling multiple requests on the same connection may need a policy to stop accepting new **requests** and drain in-flight requests, in addition to closing the listener.

Conceptual registry management example (not a standalone program):

~~~java
activeConnections.add(accepted);
try {
    executor.execute(() -> {
        try (accepted) {
            handleClient(accepted);
        } catch (IOException e) {
            reportError(e);
        } finally {
            activeConnections.remove(accepted);
        }
    });
} catch (RejectedExecutionException e) {
    activeConnections.remove(accepted);
    try {
        accepted.close();
    } catch (IOException closeError) {
        e.addSuppressed(closeError);
    }
    throw e;
}
~~~

`activeConnections` must be thread-safe and synchronized with shutdown state so there is no race between registration, submission, and force-close. The names `accepted`, `executor`, `handleClient`, and `reportError` are provided by the application. `handleClient` throws `IOException`; runtime exceptions also need an appropriate handling/logging policy. Establish clear ownership rules before choosing a collection or framework.

## 10. Timeouts, Blocking, and Error Classification

The listener and accepted sockets have **independent timeouts**:

~~~java
listener.setSoTimeout(3_000);
Socket accepted = listener.accept(); // timeout for accept()
~~~

If no connection arrives within the time limit, `accept()` throws `SocketTimeoutException`; the listener does not close itself just because of a timeout.

~~~java
try (Socket accepted = listener.accept()) {
    accepted.setSoTimeout(3_000);
    int firstByte = accepted.getInputStream().read(); // timeout for read()
}
~~~

`Socket.setSoTimeout()` limits blocking **reads on this connection**; it does not automatically apply to `ServerSocket.accept()` or to any other accepted socket. It is neither a total transaction timeout nor a write timeout.

| Issue | Common Origin | Response |
| --- | --- | --- |
| `BindException` | Listener `bind()`/constructor | Misconfigured endpoint or port in use; cannot serve yet |
| `SocketTimeoutException` on accept | `ServerSocket.accept()` | No client within timeout; can check state and continue accepting |
| `SocketTimeoutException` on read | `Socket.getInputStream().read()` | A slow client, incomplete data frame; handle per protocol |
| `SocketException` when listener closes | Waiting `accept()` | If planned shutdown, exit loop; otherwise diagnose error |
| `IOException` during client read/write | Accepted socket handler | Handle/close that connection; do not stop the entire listener by default |
| `RejectedExecutionException` | Executor rejects additional task | Caller closes the unhanded accepted socket |
| `ExecutionException` | `Future.get()` | Inspect cause to see what error the worker hit |

A framing error on one client does not mean the listener has failed. Conversely, if the server socket cannot bind, there is no valid endpoint to accept on. Logging and recovery should separate **listener-level** errors from **connection-level** errors.

TCP is a byte stream: `read()` may return fewer bytes than requested. `readLine()` waits for a newline or EOF; `InputStream.available()` does not determine whether a complete message has been received. Each handler needs framing (line delimiter, length prefix, etc.), frame limits, timeouts, and resource controls; do not turn `accept()` into a way of defining message boundaries.

## 11. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Using the listener to read the client body | `ServerSocket` has no per-client stream | Use the `Socket` returned from `accept()` |
| Creating `new ServerSocket(samePort)` per client | Bind conflict, wrong architecture | Bind the listener once and accept multiple times |
| Assuming `accept()` "turns" the listener into a client socket | Loss of lifecycle boundary | Keep the listener; the accepted socket is a separate object |
| Closing accepted A and thinking B/listener also close | Connection B still exists | Close each accepted socket per handler |
| Closing the listener and thinking all accepted sockets closed | Old workers still hold I/O and resources | Drain/close accepted sockets separately |
| `try (accepted)` in caller on async handoff | Closes socket before the task runs | Handler takes ownership and closes it |
| Executor rejects but caller does not close accepted | File descriptor/connection leak | Caller closes when task handoff fails |
| Using `accepted.getPort()` as the server port | Confuses with remote port | Use `getLocalPort()` on listener or accepted |
| Thinking backlog is the max total clients | Wrong load-capacity decisions | Distinguish backlog, active connections, and worker pool |
| Setting listener timeout and thinking client reads time out | Handler may wait for data forever | Set `SO_TIMEOUT` on each accepted `Socket` |
| Retrying `accept()` forever on planned stop even though listener is closed | Hot error loop | Exit based on shutdown state |
| Only calling `shutdownNow()` without closing sockets | Workers may remain stuck in I/O | Use a deadline and close owned sockets |
| Letting each slow client stop the server from accepting others | Blocking handling directly on accept thread | Use appropriate workers/concurrency |
| Treating `close()` as business-level success confirmation | Replies/ACKs may be lost | Use an application-layer acknowledgment protocol |

## 12. Practice Checklist

- [ ] I clearly distinguish the `ServerSocket` listener from the `Socket` for each client.
- [ ] The listener is bound once to the right local address/port.
- [ ] `accept()` runs in a loop with a clear stop mechanism.
- [ ] Each accepted socket has a single owner responsible for closing it.
- [ ] On async task handoff, the caller does not close the socket before the worker finishes.
- [ ] If the executor rejects, the unhanded socket is cleaned up.
- [ ] Per-connection timeouts and framing are in place, not just a listener timeout.
- [ ] Concurrency, queue size, and active connections are bounded.
- [ ] Shutdown has a phase to stop accepting and a phase to drain/close existing connections.
- [ ] An error on one connection does not automatically become a failure of the entire listener.
- [ ] Metrics and logs distinguish accepted/active/error counts at the right layer.
- [ ] I do not mistake `close()` or TCP FIN for confirmation that a request succeeded.

## 13. Exercises with Answers

**Exercise 1.** A server calls `accept()` successfully twice, receiving A and B. How many socket types/resources are involved on the server side?

**Answer:** One `ServerSocket` listener and two `Socket` instances for A/B. The two accepted sockets are two independent connections, which can share the listener's local port.

**Exercise 2.** Does closing accepted A automatically stop the listener from accepting new connections? Does B get closed with it?

**Answer:** No. `acceptedA.close()` only closes connection A. If the listener is still open, it can accept more clients; B is not closed automatically.

**Exercise 3.** When the server closes the listener after accepting A, can handler A still send a reply?

**Answer:** Yes, it can. Accepted socket A is still a valid and independent connection; the listener only stops accepting new clients. To block A, you must close A or ask the handler to cancel.

**Exercise 4.** Why is the following snippet wrong for asynchronous handling?

~~~java
try (Socket s = listener.accept()) {
    executor.submit(() -> handleClient(s));
}
~~~

**Answer:** Socket `s` is closed immediately upon exiting the `try` block, while the task may not have finished running. Move `try (s)` into the worker; if `submit` is rejected, the caller is responsible for closing it.

**Exercise 5.** A listener binds `127.0.0.1:7000` with backlog 32; an accepted socket has remote port 50123. Which port should the next client connect to? Is backlog 32 the maximum number of connections handled over the server's lifetime?

**Answer:** Connect to port 7000. Port 50123 is the connecting client's port. Backlog is the OS queue for connections waiting to be accepted, not a limit on the total number of clients served.

**Exercise 6.** You call `listener.setSoTimeout(1000)` and `accept()` times out. Does the listener close automatically? Do accepted sockets automatically get a 1000 ms read timeout?

**Answer:** No. The listener's timeout applies to `accept()`, whereas `setSoTimeout()` on an accepted `Socket` applies to blocking reads on that connection.

**Exercise 7.** During shutdown, a server has 100 running accepted sockets. Is closing only the listener enough to release all connections?

**Answer:** Not yet. Closing the listener stops accepting new ones; the server also needs to drain or force-close accepted sockets by a deadline and shut down the workers/executor.

## 14. Official References

- [JDK 17 — `java.net.ServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): bind, accept, close, timeout, local endpoint.
- [JDK 17 — `java.net.Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): input/output streams, local/remote endpoints, close, and half-close.
- [JDK 17 — `java.net.InetSocketAddress`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): IP/hostname and port representation.
- [JDK 17 — `java.net.SocketTimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html): timeouts in socket I/O.
- [JDK 17 — `java.util.concurrent.ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, shutdown, and worker handling.
- [Oracle Java Tutorials — All About Sockets](https://docs.oracle.com/javase/tutorial/networking/sockets/): basic TCP client/server model.

**Takeaway:** `ServerSocket` accepts connections; `accept()` creates a `Socket` used to serve each client individually. The two socket types have **separate ownership, data, timeouts, and closing lifecycles**. When those scopes are properly separated, a server can accept multiple clients, tolerate per-connection errors, and perform controlled shutdowns.
