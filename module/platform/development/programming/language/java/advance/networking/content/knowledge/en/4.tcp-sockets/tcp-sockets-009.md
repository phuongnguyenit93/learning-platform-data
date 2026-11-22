# Closing Sockets, Closing Streams, and Resource Management with try-with-resources

A TCP connection using `java.net.Socket` typically has **two byte streams**: an `InputStream` for receiving and an `OutputStream` for sending. Beyond those two streams, the operating system also holds connection resources such as socket descriptors, buffers, and TCP state. If an error path skips closing the socket, the application may hold connections and resources longer than expected. Conversely, accidentally closing a stream too early can cut off the **entire connection**, breaking the two-way exchange.

This lesson focuses on **who owns the socket, when to close a socket or stream, what `try-with-resources` guarantees, and when `shutdownOutput()` is needed instead of `close()`**. The examples use Java 17+, blocking `Socket`/`ServerSocket`, and TCP loopback; no external libraries are required.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the lifecycle of `ServerSocket`, client `Socket`, `Socket` returned by `accept()`, and the two streams associated with a `Socket`.
- Clearly understand: **closing a stream obtained from a socket also closes the socket**, and **closing a socket also closes both the input and output streams**.
- Write `try (Socket socket = ...)` with the proper scope; avoid leaks when `connect()`, reading, writing, or data processing throws an exception.
- Distinguish between `flush()`, `close()`, `shutdownOutput()`, `shutdownInput()`, and protocol-level termination signaling.
- Understand how `try-with-resources` closes resources in reverse order, preserves the primary exception, and records `suppressed exceptions`.
- Properly close resources on both client and server and when using threads/executors; avoid cutting off a connection currently in use by another worker.
- Run two examples: (1) a client/server with a response, safely releasing sockets; (2) half-close to signal the end of request data while still reading the response.

## 2. Who Owns Which Resource?

It is necessary to separate the **listening socket** from the **connected socket**, and to distinguish a stream as a **view** of a connection from an independent connection.

| Resource | Created/Obtained via | Role | Who is usually responsible for closing? |
| --- | --- | --- | --- |
| `ServerSocket` | `new ServerSocket(...)` or `new ServerSocket()` then `bind()` | Listen for TCP; `accept()` | The component owning the server/listener lifecycle |
| Client-side `Socket` | `new Socket()`, `connect(...)` | Connect to server | Client code owning the connection, or a connection pool |
| Server-side `Socket` | `listener.accept()` | Dedicated connection to one client | Handler/worker taking ownership after `accept()` |
| `InputStream` | `socket.getInputStream()` | Read bytes received from peer | Usually closed **via the socket** in an enclosing scope |
| `OutputStream` | `socket.getOutputStream()` | Write bytes to peer | Usually closed **via the socket**; `flush()` if buffered |
| `BufferedReader`, `BufferedWriter` | Wrappers around streams and character encoders/decoders | Line reading / buffered writing | Must be aware that wrapper `close()` propagates down to the stream/socket |
| `ExecutorService`/worker task | `Executors...`, thread | Handle multiple connections or run demo server | The creator of the executor must manage shutdown and wait for work to finish when needed |

Lifecycle diagram in a TCP server:

~~~text
ServerSocket (LISTEN)
  |
  +-- accept() --> Socket client A --+-- InputStream A  (read from A)
  |                                 +-- OutputStream A (write to A)
  |
  +-- accept() --> Socket client B --+-- InputStream B
                                    +-- OutputStream B

close(Socket A)     -> closes only connection A and its streams
close(ServerSocket) -> stops listening/accepting; does not automatically close B if B is still alive
~~~

**Design rule:** each independently owned resource should have one **owner** responsible for closing it. Do not close a socket borrowed from a connection pool in code that does not hold ownership, and do not hand off a socket to another worker and close it in the caller before the worker finishes using it. When a handler truly owns an accepted socket, `try-with-resources` inside the handler is the natural place to close it.

## 3. What Does `Socket.close()` Do?

`Socket` implements `java.io.Closeable` (and `AutoCloseable`), so it can be used with `try-with-resources`. According to the JDK `Socket` API:

1. `socket.close()` makes the socket no longer usable for network I/O; the same object cannot be reconnected.
2. It **closes both streams** returned by `getInputStream()` and `getOutputStream()`.
3. Any thread currently blocked in I/O on the closed socket will receive a corresponding error (with standard blocking `Socket`, a `SocketException`).
4. `close()` is **local** cleanup. It does not guarantee that the peer application has finished processing the message just sent; an **application-level** acknowledgment response is needed if that requirement matters.
5. `isClosed()` indicates whether the object has been closed. **`isConnected()` is not a check for whether the connection is still active**: a socket that once connected successfully can still return `true` after being closed.

State check example:

~~~java
Socket socket = new Socket();
// After socket.connect(...) succeeds:
try (socket) {
    // Exchange data within the connection scope.
}
System.out.println(socket.isClosed()); // true
// socket.isConnected() may still be true because it was once connected.
~~~

This snippet is **illustrative code**; it requires importing `java.net.Socket`, a real endpoint, and handling `IOException`. Do not treat `isConnected()` as a heartbeat mechanism or a check for whether the peer is alive; reading/writing with protocol timeouts is what reflects the actual interaction state.

### Closing `ServerSocket` Does Not Equal Closing Accepted `Socket`s

When a server accepts a connection via `Socket accepted = listener.accept()`, `accepted` is a **new resource**. Closing `listener` causes a waiting `accept()` to be interrupted with a `SocketException`, but already-accepted `Socket`s **do not automatically close with the listener**. The server must manage each accepted connection, especially when handing them off to a thread pool.

When a TCP server stops in a controlled manner, one way to organize this is: stop accepting new connections → close the listener to release the `accept` thread → let in-flight requests finish within a deadline → close remaining accepted sockets → shut down the executor. The timing of closing each socket must align with the protocol and service requirements.

## 4. Closing a Socket's Stream: A Commonly Misunderstood Effect

`Socket.getInputStream()` and `Socket.getOutputStream()` return streams **tied to the same socket**. The JDK specifies:

- Calling `socket.getInputStream().close()` will close the associated socket.
- Calling `socket.getOutputStream().close()` will close the associated socket.
- Closing `BufferedReader`, `InputStreamReader`, `BufferedWriter`, or `OutputStreamWriter` typically closes the stream they wrap; at the end of that chain, it can **close the socket as well**.

This differs from the assumption that "closing input only forbids reading, while output can still send normally." With a Java `Socket`, **closing a base stream from the socket closes the entire socket**. To close **one direction** while continuing with the other, see `shutdownOutput()`/`shutdownInput()` later.

### Incorrect Example When Waiting for a Response

~~~java
// Illustrates a logic bug in a method that already has a Socket socket.
try (OutputStream out = socket.getOutputStream()) {
    out.write("REQUEST".getBytes(StandardCharsets.US_ASCII));
} // out.close() -> also closes the socket!

// Error: the socket is already closed, cannot continue reading the response normally.
InputStream in = socket.getInputStream();
~~~

Here `try-with-resources` itself behaves **according to its contract**, but the resource scope was chosen incorrectly. You cannot fix this by removing `try-with-resources` and forgetting to close the socket; you must clearly design ownership and closing time.

### Recommended Pattern: Let `Socket` Be the Primary Owner

~~~java
try (Socket socket = new Socket()) {
    socket.connect(address, 2_000);
    socket.setSoTimeout(3_000);

    BufferedReader in = new BufferedReader(new InputStreamReader(
            socket.getInputStream(), StandardCharsets.UTF_8));
    BufferedWriter out = new BufferedWriter(new OutputStreamWriter(
            socket.getOutputStream(), StandardCharsets.UTF_8));

    out.write("PING\n");
    out.flush();
    String response = in.readLine();
    // Parse response, then exit scope.
} // socket.close() closes the connection and associated streams.
~~~

This is a **code snippet inside a method**: `address` needs to be an already-created `SocketAddress`, and the method must declare `throws IOException` or have a `catch`. Required imports: `java.net.Socket`, `java.net.SocketAddress`, `java.io.*`, `java.nio.charset.StandardCharsets`. When wrappers are kept in the same scope and explicitly `flush()`ed, managing via a **single socket owner** prevents wrappers from closing the socket prematurely.

Note: because the wrappers are not declared as separate resources in this example, if there are still bytes sitting in the **Java-side buffer** that have not been `flush()`ed, `socket.close()` is not guaranteed to automatically flush the wrapper. You must complete writing/flushing per the protocol before closing. When using only one direction (for example, reading an entire response and then closing the connection), putting the wrapper in `try-with-resources` can also be reasonable **if you accept that closing the wrapper terminates the socket**.

## 5. How `try-with-resources` Guarantees Cleanup

Since Java 7, `try-with-resources` automatically calls `close()` on objects implementing `AutoCloseable`. Since Java 9, a previously declared resource variable can be placed in `try (socket)` if that variable is final or effectively final.

~~~java
try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress("127.0.0.1", 9000), 2_000);
    // Whether the try body finishes, returns, or throws an exception, socket is still closed.
}
~~~

This is an illustrative snippet inside a method that declares/catches `IOException`. There is no listener on port 9000 in this lesson, so do not expect running that snippet alone to succeed. Using `new Socket()` and then calling `connect()` **inside** the try block has an advantage: the already-created socket will be closed even if `connect()` or a subsequent operation fails.

### 5.1. Closing Order with Multiple Resources

Resources are closed in the **reverse order of their declaration**:

~~~java
try (ResourceA a = openA();
     ResourceB b = openB()) {
    doWork(a, b);
}
// close(b) runs before close(a).
~~~

This is **pseudocode**, not a standalone runnable Java program because `ResourceA`, `ResourceB`, `openA`, and `doWork` are not declared. With a socket and wrappers, for example:

~~~java
try (Socket socket = connect();
     BufferedReader reader = new BufferedReader(
             new InputStreamReader(socket.getInputStream(), UTF_8));
     BufferedWriter writer = new BufferedWriter(
             new OutputStreamWriter(socket.getOutputStream(), UTF_8))) {
    // Two-way communication within scope.
}
// close(writer) -> close(reader) -> close(socket)
~~~

This is also an **illustrative snippet** with `connect()` and `UTF_8` undefined. Linguistically, the structure is valid once those identifiers are replaced; however, closing `writer` will close the socket before `reader` is closed, making the repeated closes redundant. **Choose one consistent ownership model**; there is no need to put every stream wrapper into the resource list just for formality.

### 5.2. Exceptions Occurring in the try Body and During close

If the `try` body throws an exception and `close()` also throws an exception, **the exception in the try body remains the primary exception**, and the exceptions thrown during closing are attached as **suppressed**. If no exception occurred in the body but `close()` fails, the closing error becomes the thrown exception.

~~~java
try (Socket socket = new Socket()) {
    socket.connect(endpoint, 2_000);
    performExchange(socket);
} catch (IOException e) {
    reportFailure(e); // primary error
    for (Throwable suppressed : e.getSuppressed()) {
        reportFailure(suppressed); // error occurring while closing resource
    }
}
~~~

This is an illustrative code snippet inside a method; `endpoint`, `performExchange`, and `reportFailure` are application-defined. You should not write `catch (Exception e) {}` and swallow errors: doing so can lose information about both the transaction and cleanup. In real systems, log exceptions with necessary context, while avoiding logging passwords, tokens, or sensitive user data.

### 5.3. Comparison with Manual `finally`

~~~java
Socket socket = null;
try {
    socket = new Socket();
    // ...
} finally {
    if (socket != null) socket.close();
}
~~~

The snippet above can work, but you must handle `close()` throwing `IOException` yourself and risk **masking the primary error** if cleanup also fails. `try-with-resources` is simpler and has clear suppressed-exception rules. `finally` is still useful for other things, such as calling `executor.shutdownNow()` after the listener/sockets have closed; do not use a redundant `finally` just to re-close a socket that is already in the resource list.

## 6. `flush()`, EOF, and When to Close: Follow the Protocol

### 6.1. `flush()` Is Not `close()`

`BufferedWriter`, `BufferedOutputStream`, or other buffering layers may hold bytes **in application memory** before passing them down to the underlying stream. `flush()` pushes buffered bytes down to the underlying stream; it **does not mean the peer has received or finished processing them**. For data that needs an immediate reply, you must `flush()` before waiting for a response.

~~~java
BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(
        socket.getOutputStream(), StandardCharsets.UTF_8));
writer.write("HELLO\n");
writer.flush();     // Send buffered bytes to the socket before waiting for the peer.
~~~

If `flush()` is omitted, the client may wait for the server's reply while the server waits for request bytes that have not been pushed out of the buffer: creating a logical deadlock. Calling `flush()` after the stream/socket is already closed cannot restore the connection.

### 6.2. TCP Is a Byte Stream, Not "One Read Equals One Message"

`InputStream.read()` returns the number of bytes read, or `-1` when EOF is reached and no more data bytes remain in the stream; it may return fewer bytes than the requested buffer size. `BufferedReader.readLine()` reads until a newline character or EOF; if the peer never sends a newline and never closes its sending direction, `readLine()` can keep waiting.

Therefore, the protocol must define **message boundaries**. Some approaches:

- Line-delimited: `PING\n`, `PONG\n`. Requires agreeing on a charset and a maximum line length.
- Length-prefixed: send the payload byte count first, then read that exact number of bytes.
- Read to EOF: only appropriate when the sender **signals the end of data** by closing its sending direction/connection, and the receiver has a clear termination rule.

Do not use `InputStream.available() == 0` to infer that a message has ended: 0 only means no bytes are currently available to read immediately under present conditions.

### 6.3. Closing After Writing Does Not Prove the Peer Succeeded

The sequence `write(...) -> flush() -> close()` indicates that the application handed bytes to the I/O layers per each method's contract and then terminated the connection; it does not produce an **application-level acknowledgment**. The peer may lose the connection, reject the request, or fail before committing the data.

If business-level guarantees are needed, design **response/ACK**, timeouts, retries, and idempotency. For payment commands, data writes, resource deletions, etc., do not assume that "close did not throw an error" means the transaction completed.

## 7. `close()` vs. Half-Close: How Do They Differ?

TCP has two independent directions. `Socket.shutdownOutput()` ends the **sending direction** of the socket while allowing you to continue **reading the receiving direction**. This is a useful tool for a "client sends the entire request, then server returns the result" protocol.

| Operation | Sending direction | Receiving direction | Is the socket still usable for communication? |
| --- | --- | --- | --- |
| `socket.close()` | Closed | Closed | **No**, the entire socket is closed |
| `socket.shutdownOutput()` | Sending closed; cannot write more | Can still read | **Yes**, used to read the response; close socket afterward |
| `socket.shutdownInput()` | Can still send | Receiving ended locally; further reads report EOF | **Yes** at the object level, but further incoming data will be discarded |
| `output.flush()` | Pushes buffered data downstream | Unchanged | **Yes**, terminates neither direction |
| `output.close()` on a socket stream | Closes the **entire socket** | Also closed | **No**, because closing the stream closes the socket |

With TCP, `shutdownOutput()` produces a send-direction termination signal according to TCP semantics (FIN after written data), not "sending an empty message." Afterward, calling `getOutputStream().write(...)` again will throw `IOException`. `shutdownOutput()` **does not close the socket object completely**; you still must use `try-with-resources` or `close()` when finished reading.

`shutdownInput()` is an operation with a different effect: the JDK states that subsequent reads return `-1`, and data the other side continues sending toward the receiving direction will be acknowledged and discarded. It is not the default way to finish a transaction; it is very easy to lose a response if called by mistake.

**Important practical point:** If using `BufferedWriter`, you must call `writer.flush()` **before** `socket.shutdownOutput()`. Simply calling `shutdownOutput()` cannot automatically flush content still sitting in `BufferedWriter`'s buffer.

## 8. Example 1: Client and Server Safely Using `try-with-resources`

The following program runs both a TCP listener and a client on the local machine. The server receives a single line `PING`, replies `PONG`, and then closes the accepted socket. The client waits for the response, exits the `try` scope, and verifies `isClosed()`. Both server and client use the **socket as the owner**. Read/write wrappers live in the same scope and `flush()` before waiting for a response.

Create the file **`SocketCloseDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            listener.setSoTimeout(3_000);

            Future<?> serverTask = workers.submit(() -> {
                try (Socket accepted = listener.accept()) {
                    accepted.setSoTimeout(3_000);

                    BufferedReader input = new BufferedReader(
                            new InputStreamReader(
                                    accepted.getInputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedWriter output = new BufferedWriter(
                            new OutputStreamWriter(
                                    accepted.getOutputStream(),
                                    StandardCharsets.UTF_8));

                    String request = input.readLine();
                    if (!"PING".equals(request)) {
                        throw new IOException("Unexpected request");
                    }
                    output.write("PONG\n");
                    output.flush();
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });

            Socket client = new Socket();
            try (client) {
                client.connect(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort()), 2_000);
                client.setSoTimeout(3_000);

                BufferedReader input = new BufferedReader(
                        new InputStreamReader(
                                client.getInputStream(),
                                StandardCharsets.UTF_8));
                BufferedWriter output = new BufferedWriter(
                        new OutputStreamWriter(
                                client.getOutputStream(),
                                StandardCharsets.UTF_8));

                output.write("PING\n");
                output.flush();
                System.out.println("Client received: " + input.readLine());
            }
            System.out.println("Client closed: " + client.isClosed());
            serverTask.get(5, TimeUnit.SECONDS);
        } finally {
            workers.shutdownNow();
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 SocketCloseDemo.java
java SocketCloseDemo
~~~

**Verified stdout on Java 24** (the behavior of the APIs used also applies to Java 17+):

~~~text
Client received: PONG
Client closed: true
~~~

Explanation:

1. `listener.bind(..., 0)` lets the OS pick an available port; loopback is used so no external network is needed. `ServerSocket` is in the resource list and will close at the end of the scope.
2. `workers.submit(...)` runs the server handler; `listener.accept()` creates a **new Socket**. `try (Socket accepted = ...)` closes this individual connection even if the handler throws `IOException`.
3. `BufferedReader.readLine()` waits for a newline. The client sends `PING\n` and **flushes**; the server sends `PONG\n` and **flushes**.
4. `Socket client = new Socket(); try (client)` uses Java 9+ syntax, ensuring closure even if `connect()`, `readLine()`, or processing logic throws an exception.
5. After exiting `try (client)`, `client.isClosed()` is `true`. There is no need to close individual streams separately.
6. `serverTask.get(...)` waits for the handler to finish and propagates any task exception to the caller. `finally` shuts down the executor; closing the listener and accepted socket is handled by their respective scopes.

The example handles only **one** connection, one request line, and one response line. This is educational code about lifecycle; a production service must have request limits, concurrency policies, logging, authentication when appropriate, and controlled stop/shutdown management. Timeouts of a few seconds are demo values and should be designed for the real environment.

## 9. Example 2: `shutdownOutput()` to Signal End of Request and Still Receive ACK

This example illustrates a **read-to-EOF** protocol: the client sends `HELLO`, signals it has finished sending via `shutdownOutput()`, and the server reads the entire request and replies `ACK:5`. The client continues reading the ACK before the socket is closed. If `client.getOutputStream().close()` were called instead of `shutdownOutput()`, the entire socket would be closed and could no longer be used to read the ACK.

Create the file **`SocketHalfCloseDemo.java`**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketHalfCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {
            Future<?> serverTask = workers.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(3_000);
                    byte[] request = peer.getInputStream().readAllBytes();
                    String reply = "ACK:" + request.length + "\n";
                    peer.getOutputStream().write(
                            reply.getBytes(StandardCharsets.US_ASCII));
                    peer.getOutputStream().flush();
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort()), 2_000);
                client.setSoTimeout(3_000);
                client.getOutputStream().write(
                        "HELLO".getBytes(StandardCharsets.US_ASCII));
                client.shutdownOutput();
                byte[] reply = client.getInputStream().readAllBytes();
                System.out.print(new String(
                        reply, StandardCharsets.US_ASCII));
            }
            serverTask.get(5, TimeUnit.SECONDS);
        } finally {
            workers.shutdownNow();
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 SocketHalfCloseDemo.java
java SocketHalfCloseDemo
~~~

**Verified stdout:**

~~~text
ACK:5
~~~

Here the server's `readAllBytes()` knows when to stop because the client **half-closed the sending direction**; after the server writes the ACK, the server closes the accepted socket, so the client receives EOF and finishes `readAllBytes()`. If the client only called `flush()` without `shutdownOutput()`, the server waiting for EOF could keep waiting; both sides risk getting stuck.

**Limitations of the example:** `readAllBytes()` can consume memory proportional to the size of the received data. It is only suitable here because the input is the self-generated, very short string `HELLO`. With untrusted network data, you need byte limits, quotas, protocol framing, and deadlines. In production two-way protocols, explicit frame lengths or delimiters are typically used instead of forcing every request to end with EOF.

## 10. Timeouts, Cancellation, and Error Handling on Close

Using `try-with-resources` prevents leaks, but cleanup **does not automatically solve** all cases of indefinite blocking.

| Configuration/Operation | Limit or effect | What must not be inferred |
| --- | --- | --- |
| `socket.connect(endpoint, 2_000)` | Timeout for the TCP connection establishment step | Does not bound the entire request/response |
| `socket.setSoTimeout(3_000)` | Timeout for **blocking read** operations on the socket | Not a timeout for every `write()` or the total transaction |
| `listener.setSoTimeout(3_000)` | Bounds a single blocking `accept()` call | Does not automatically close the listener after timeout |
| `socket.close()` | Closes the socket; wakes threads stuck in socket I/O with an exception per contract | Does not confirm the peer's business processing is complete |
| `listener.close()` | Stops the listener; causes a waiting `accept()` to fail | Does not automatically close accepted sockets already handed to workers |
| `executor.shutdown()` | Stops accepting new tasks, gives existing tasks a chance to finish | Does not automatically close sockets held inside tasks |
| `executor.shutdownNow()` | Requests interruption/cancellation of running tasks | Not a reliable socket-closing mechanism across all I/O implementations |

In a server with a thread pool, you need to track live accepted sockets or have an appropriate cancellation mechanism; when a forced stop is required, **close the sockets owned by the server** to release blocking I/O. Do not assume `Thread.interrupt()` has the same effect as `Socket.close()` across all Socket/JDK implementations.

### Handling `SocketTimeoutException`

`SocketTimeoutException` is an `IOException`; a read timeout usually does not cause the socket to close itself. However, whether you can keep using the connection or must discard it depends on the **protocol's framing state**: a partial message may have been received. If a consistent frame cannot be recovered, close the socket and start a new connection/transaction as specified.

### When `close()` Also Fails

`close()` can throw `IOException`. Do not write a `finally` block that tries to swallow errors, or throw a new exception that masks the original cause. `try-with-resources` preserves the primary exception and attaches cleanup errors to `getSuppressed()`. With a large number of resources, log errors at an appropriate level while avoiding repetitive logging or missing context. An exception on close does not mean the caller should continue using the same socket; the safe design is to treat the scope as ended.

### `SO_LINGER` and Abnormal Termination

`setSoLinger(true, 0)` can turn a close into a reset/abort termination instead of a normal TCP close, risking loss of data not yet read by the other side. A positive `SO_LINGER` value can affect how long close blocks. Do not arbitrarily enable linger or rely on port release timing to prove a transaction completed. If you need confirmation of processing at the peer, use an **application-protocol ACK**.

## 11. Ownership Rules in Large Applications

### 11.1. Client Creating Its Own Socket for a Transaction

Basic pattern:

~~~java
try (Socket socket = new Socket()) {
    socket.connect(endpoint, connectTimeoutMillis);
    socket.setSoTimeout(readTimeoutMillis);
    exchange(socket);
}
~~~

This is an **illustrative code snippet**; `endpoint`, `connectTimeoutMillis`, `readTimeoutMillis`, and `exchange` are caller-defined. The calling method declares/catches `IOException`. If `exchange()` can manage both directions, **the caller is the owner** and closes at the transaction boundary; the helper does not close the socket itself before the caller finishes.

### 11.2. Handler Receiving an Accepted Socket

~~~java
while (running) {
    Socket accepted = listener.accept();
    handleOneConnection(accepted); // Must have a contract: transfer ownership.
}
~~~

This snippet **describes control flow**, not a standalone runnable program (variables/methods must be declared). If `handleOneConnection` owns the socket, place `try (accepted)` **inside the handler**. If the caller retains ownership, the caller must close it. Never leave both sides thinking the other is responsible. With `ExecutorService.submit(() -> handle(accepted))`, if `submit` is rejected because the executor is shut down, the caller must still **close the accepted socket** because ownership transfer did not succeed.

### 11.3. Sockets Managed by a Connection Pool

When a client uses an abstraction/pool that reuses connections, `close()` on the wrapper object may return the connection to the pool rather than closing the actual TCP connection, depending on the library. For **`java.net.Socket` directly**, `close()` closes the connection as defined by the API. Do not apply raw-socket rules verbatim to wrappers/pools without reading the library's ownership contract.

### 11.4. Note on TLS

`SSLSocket` also belongs to the socket family, but TLS has its own handshake and secure shutdown procedure. If an application uses `SSLSocket`, follow the JSSE documentation and TLS semantics; do not assume `shutdownOutput()` on raw TCP is a valid TLS termination in all cases. This lesson focuses on plain `java.net.Socket`.

## 12. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | Solution |
| --- | --- | --- |
| Only creating `new Socket()` and forgetting `close()` on error | Descriptors and connections can outlive their expected lifetime | `try (Socket socket = ...)` enclosing `connect()` and the transaction |
| Closing `InputStream` to "just stop reading" | Closing a stream from a socket **closes the entire socket** | Use `shutdownInput()` only if the protocol requires it; usually just finish reading and `close()` |
| `try (OutputStream out = socket.getOutputStream())` then still wanting to read a response | `out.close()` closes the socket before reading | Make the socket the owner; if one-way EOF is needed, `flush()` then `shutdownOutput()` |
| Closing `BufferedWriter` before the server responds | Wrapper close propagates to the socket | `flush()` the writer, read the response, then end the socket scope |
| Assuming `socket.close()` automatically `flush()`es all wrapper buffers | Wrappers may still hold bytes in Java memory | Flush per protocol before closing |
| Assuming `flush()` guarantees the peer processed the request | Flush only pushes data through buffer layers | Wait for a valid response/ACK if confirmation is needed |
| Omitting the delimiter and waiting on `readLine()` | Peer waits for newline/EOF, so it can hang | Define framing, send newline, flush |
| Treating `read() == -1` as meaning the request succeeded | EOF only signals end of stream; peer may have disconnected early | Verify complete frame, status, and ACK |
| Relying on `isConnected()` to check if a socket is alive | It can remain true after close | Manage lifecycle with `isClosed()`, I/O operations, and protocol |
| Closing `ServerSocket` and thinking all clients are disconnected | Accepted sockets are independent | Track the list of connections/workers and close them separately |
| Closing the socket in the caller while a task is still using it | Worker gets `SocketException`, loses messages | Clearly define the ownership transfer point and close timing |
| Only calling `shutdownNow()` on the executor | Interrupt does not always unblock socket I/O | Have timeouts, close listener/accepted sockets per policy |
| Swallowing `IOException` or suppressed exceptions | Loses information about transaction and cleanup errors | Record/provide context, preserve root cause |
| Using `readAllBytes()` on arbitrary network payloads | Can consume excessive memory or wait for EOF indefinitely | Bound sizes, use framing and deadlines |
| Enabling `SO_LINGER` without reason | Can reset the connection or cause close to block | Keep default unless there is a clear requirement and testing |

## 13. Pre-Run Code Checklist

- [ ] Identified the **owner** for the listener, client socket, and each accepted socket.
- [ ] Every owned socket is inside `try-with-resources` or equivalent cleanup with a clear lifecycle.
- [ ] `connect()` is performed **inside** the resource scope so failed connections are still closed.
- [ ] Stream wrappers are not closed before the two-way exchange completes.
- [ ] Bytes written via `BufferedWriter`/`BufferedOutputStream` are `flush()`ed at the points required by the protocol.
- [ ] The protocol has **framing** and a termination condition; does not wait on `readLine()`/EOF indefinitely.
- [ ] If half-close is needed, I use `shutdownOutput()` after writing/flushing and still close the socket when finished reading.
- [ ] Appropriate connection timeout, read timeout, and business deadline are configured.
- [ ] Accepted sockets are still managed when the listener/executor stops.
- [ ] Error paths preserve the root cause and inspect suppressed exceptions when cleanup issues occur.
- [ ] I do not use `close()`, `flush()`, or TCP FIN as proof that the peer application succeeded.
- [ ] Tests cover happy path, timeout, premature peer close, processing errors, and connection cancellation.

## 14. Self-Check Exercises with Answers

**Exercise 1.** A TCP client writes a request via `BufferedWriter`, calls `writer.close()`, and then calls `reader.readLine()` on the same socket. Why can this fail?

**Answer:** `BufferedWriter.close()` closes the underlying writer/output stream chain; closing an output stream obtained from `Socket` closes the **entire socket**, so the reading direction also becomes invalid. Keep the socket as the owner, `flush()`, and then read the response; if the server requires EOF before processing, use `shutdownOutput()` after flushing.

**Exercise 2.** Does `ServerSocket.close()` guarantee that already-accepted sockets are also closed?

**Answer:** No. The listener only stops listening/accepting. Each accepted socket has its own lifecycle and must be closed by its handler or a server shutdown manager.

**Exercise 3.** The `try-with-resources` body throws `IOException A`; during `close()`, `IOException B` is also thrown. Which error is the primary exception?

**Answer:** A is the primary exception; B is attached in `A.getSuppressed()`. If only close fails while the try body does not throw, the close exception can be the primary error.

**Exercise 4.** The server calls `readAllBytes()` waiting for EOF; the client has called `write()` and `flush()` and is waiting for the server to return a result. Can both sides get stuck?

**Answer:** Yes. If the server protocol reads until EOF, `flush()` does not signal EOF. The client needs `shutdownOutput()` to finish the sending direction and then read the result; afterward, `close()` the socket. Even better, use explicit framing if you want multiple transactions over one connection.

**Exercise 5.** Does `isConnected()` returning `true` mean the socket can still send data?

**Answer:** No. It records that the object was once connected; it can still be `true` after `close()`. You must manage the lifecycle and handle I/O/timeout errors per the protocol.

**Exercise 6.** Does `Socket.setSoTimeout(3000)` force every `write()` and `close()` to finish within 3 seconds?

**Answer:** No. `SO_TIMEOUT` on `Socket` applies to blocking **read** operations. Connecting has its own timeout in `connect(endpoint, timeout)`; overall transaction, write, and close deadlines require appropriate policies/architecture, rather than conflating them with the read timeout.

## 15. Official References

- [JDK 17 — `java.net.Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `close()`, `getInputStream()`, `getOutputStream()`, `shutdownInput()`, `shutdownOutput()`, `isClosed()`, `isConnected()`, `setSoTimeout()`.
- [JDK 17 — `java.net.ServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): listener, `accept()`, `close()`, `setSoTimeout()`.
- [Java Tutorials — The try-with-resources Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): closing resources in reverse order and suppressed exceptions.
- [JDK 17 — `java.io.BufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html): `flush()`, `close()`.
- [JDK 17 — `java.io.Closeable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): resource closing contract.
- [JDK 17 — `java.util.concurrent.ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): managing concurrent work and shutdown.

**Principles to keep in mind when programming TCP:** give each socket a clear owner; scope `try-with-resources` to cover the entire exchange; flush buffered data at the right time; use `shutdownOutput()` only when the protocol requires ending one direction; always close the socket at the end of its lifecycle and confirm completion with an application-level protocol if needed.
