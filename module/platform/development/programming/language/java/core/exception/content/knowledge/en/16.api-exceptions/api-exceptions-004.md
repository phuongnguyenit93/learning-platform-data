# SocketException, SocketTimeoutException, and Network Errors in Java

Socket programming in Java forces a program to deal with many states that are not entirely under the control of application code: an unresolvable address, a server not yet listening, a closed connection, a reset connection, no data arriving within the allowed time, no network route, or a send operation that has been performed without a response arriving. **`SocketException` and `SocketTimeoutException` are two important names, but they do not share a direct inheritance branch**.

Key takeaways to remember immediately:

- **`java.net.SocketException`** extends **`java.io.IOException`**; it generally represents an error when creating, accessing, or using a socket. Notable subclasses include `ConnectException`, `BindException`, `NoRouteToHostException`, and `PortUnreachableException`.
- **`java.net.SocketTimeoutException`** extends **`java.io.InterruptedIOException`**, which in turn extends **`IOException`**. It does **not** extend `SocketException`. It signals that a socket operation has exceeded a **timeout** supported by the API, such as connecting, reading data, `ServerSocket.accept()`, or `DatagramSocket.receive()`.
- Both are **checked exceptions** in the Java sense: they reside under `IOException`, not `RuntimeException`. The calling method must handle them or declare a checked exception type broad enough to cover them.
- **A timeout does not mean a permanent connection failure**, **EOF does not mean a timeout**, **a DNS failure does not mean connection refused**, and **socket closed does not mean the network is down**.
- You need to distinguish between **the technical error**, **acceptable retry levels**, **operation idempotency**, **transaction state**, and **how to preserve the cause/stack trace**. Relying solely on a message like `"Connection reset"` to decide whether to retry is very error-prone.

This article explains the API contracts, hierarchy, real-world scenarios, self-contained Java 17 examples using loopback without requiring Internet access, error-handling patterns, timeout limitations, testing, and a troubleshooting checklist.

## 1. Inheritance Diagram: Distinguish Before Writing `catch`

A condensed hierarchy of the relevant checked exceptions:

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.io.IOException
        ├── java.net.SocketException
        │   ├── java.net.BindException
        │   ├── java.net.ConnectException
        │   ├── java.net.NoRouteToHostException
        │   └── java.net.PortUnreachableException
        ├── java.io.InterruptedIOException
        │   └── java.net.SocketTimeoutException
        ├── java.net.UnknownHostException
        ├── java.io.EOFException
        └── ... other IOException classes
```

**Most common point of confusion:** `SocketTimeoutException` is not under `SocketException`. Both types can arise during socket operations, but they belong to **two different branches** of `IOException`.

Consequence when writing handlers:

```java
try {
    communicate();
} catch (SocketTimeoutException e) {
    // Timeout policy.
} catch (SocketException e) {
    // Other socket errors.
} catch (IOException e) {
    // Remaining I/O errors.
}
```

This is an **illustrative block**, assuming a method `communicate() throws IOException` in scope and appropriate `java.net`/`java.io` imports. This structure is valid because `IOException` comes last, while the first two types are its subclasses on separate branches.

If you only write `catch (SocketException e)`, it will **not** catch `SocketTimeoutException`. If you put `catch (IOException e)` first, the subtype handlers after it will be **unreachable** and the compiler will reject the code.

## 2. Java 17 Example: Verifying Type Relationships in Code

Save **`SocketExceptionHierarchyDemo.java`**:

```java
import java.io.IOException;
import java.io.InterruptedIOException;
import java.net.ConnectException;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

public class SocketExceptionHierarchyDemo {
    public static void main(String[] args) {
        System.out.println("SocketException <: IOException: "
                + IOException.class.isAssignableFrom(
                        SocketException.class));

        System.out.println("Timeout <: IOException: "
                + IOException.class.isAssignableFrom(
                        SocketTimeoutException.class));

        System.out.println("Timeout <: InterruptedIOException: "
                + InterruptedIOException.class.isAssignableFrom(
                        SocketTimeoutException.class));

        System.out.println("Timeout <: SocketException: "
                + SocketException.class.isAssignableFrom(
                        SocketTimeoutException.class));

        System.out.println("ConnectException <: SocketException: "
                + SocketException.class.isAssignableFrom(
                        ConnectException.class));

        System.out.println("UnknownHostException <: SocketException: "
                + SocketException.class.isAssignableFrom(
                        UnknownHostException.class));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 SocketExceptionHierarchyDemo.java
java SocketExceptionHierarchyDemo
```

**Exact stdout:**

```text
SocketException <: IOException: true
Timeout <: IOException: true
Timeout <: InterruptedIOException: true
Timeout <: SocketException: false
ConnectException <: SocketException: true
UnknownHostException <: SocketException: false
```

`Class.isAssignableFrom` checks type-assignment compatibility. The output confirms that a timeout error can be caught by `IOException` or `InterruptedIOException`, but **not** by `SocketException`.

If you do not want to catch multiple specific types, `catch (IOException e)` serves as a general fallback layer. However, **catching broadly does not mean all I/O errors share the same retry or recovery policy**.

## 3. What Kinds of Failures Does `SocketException` Describe?

`SocketException` is a checked exception used in socket operations to reflect an unsuccessful I/O or socket-usage condition. Real-world examples may include:

- The socket was closed while the program tried to use it.
- One end of a TCP connection was reset according to network stack behavior.
- A socket-layer issue caused a read, write, or connect operation to fail.
- The operating system or network stack rejected a socket-related operation.
- A subclass reports a specific situation, such as **`ConnectException`** (the connection was refused or could not be established by the underlying mechanism) or **`BindException`** (unable to bind the endpoint).

However, **you should not over-infer**:

- `SocketException` does not always mean the server is down.
- `SocketException` does not always mean network hardware is broken.
- `SocketException` does not tell you for sure whether the server-side operation was already executed or not.
- The same physical cause can appear under different exception types or messages depending on the JVM, operating system, protocol, and step being executed.
- Messages like `"Connection reset"`, `"Broken pipe"`, or `"Socket closed"` are diagnostic hints, **not standardized Java error codes across all platforms**.

You need to observe **the exception type, the operation being performed, the socket lifecycle, the address, configured timeouts, timing, and business outcome**, rather than just reading a message string.

## 4. What Does `SocketTimeoutException` Mean?

`SocketTimeoutException` is thrown when a socket operation has a **timeout** and that limit is exceeded before the operation reaches the completion condition defined by the API.

Typical contexts:

1. **Connecting:** `Socket.connect(endpoint, timeout)` fails to establish a connection within the limit.
2. **TCP reading:** `Socket.setSoTimeout(milliseconds)` sets the read timeout for applicable blocking read operations on `SocketInputStream`.
3. **Waiting for clients:** `ServerSocket.setSoTimeout(milliseconds)` limits how long `ServerSocket.accept()` waits for a new connection.
4. **Receiving datagrams:** `DatagramSocket.setSoTimeout(milliseconds)` limits how long `receive(...)` waits for a matching packet.

You should not say "timeout = 2 seconds means the entire request must finish within 2 seconds" if you only set a **read timeout**: that is the limit for a read operation waiting for data, and it does not automatically create an **overall deadline** for a workflow involving multiple reads, retries, parsing, and processing.

When a timeout occurs, the API throws an exception; **it does not mean the resource is necessarily permanently broken**. For a blocking socket read subject to `SO_TIMEOUT`, the `Socket` documentation states that the socket remains valid after a `SocketTimeoutException`, though the application layer must determine whether it can continue reading, whether message framing is still consistent, and whether there is a risk of partial data.

## 5. Checked Exceptions and the Catch-or-Declare Obligation

Both `SocketException` and `SocketTimeoutException` are subclasses of `IOException`, and therefore belong to the **checked** group. Example:

```java
static int receiveOneByte(Socket socket) throws IOException {
    return socket.getInputStream().read();
}
```

This is an **illustrative method**; it requires importing `java.net.Socket` and `java.io.IOException`. Because `getInputStream` and `read` can throw checked `IOException`, declaring `throws IOException` on the method is a valid way to delegate responsibility to the caller.

A caller can:

- `catch (SocketTimeoutException e)` to apply a timeout policy.
- `catch (SocketException e)` for specific socket errors.
- `catch (IOException e)` for other I/O errors.
- Or declare `throws IOException` to propagate it up to a layer responsible for handling it.

Not seeing `throws SocketTimeoutException` in a signature does not mean it cannot occur: a method declaring `throws IOException` still allows any appropriate subclass. Conversely, writing `throws SocketException` **does not cover** `SocketTimeoutException` because they are on different branches.

## 6. Network Error Types to Distinguish

| Type or signal | Common situation | What not to conclude |
| --- | --- | --- |
| `UnknownHostException` | Hostname could not be resolved via DNS/address lookup | Not a `SocketException`; does not mean the server refused the connection |
| `ConnectException` | TCP connection could not be established, commonly when the endpoint refuses it | No proof that the business request was executed |
| `NoRouteToHostException` | No network route to the host could be found or a similar IP-layer reason | Not the same as an application timeout |
| `BindException` | Cannot bind to a local address/port | Not a read error on an already open connection |
| `SocketTimeoutException` | Socket operation waited past its configured limit | Does not by itself prove the remote server is dead |
| `SocketException` | General socket error or unusable socket state | No single retry policy fits every message |
| `EOF` from `InputStream.read() == -1` | The sender cleanly closed its output and no more bytes remain | Not a timeout exception |
| `EOFException` | A structured reading API expected more bytes but hit EOF | Different from the `-1` return value of `InputStream.read()` |
| `SSLException` | TLS/SSL-layer issue when using the corresponding API | Not every TLS failure is a `SocketException` |
| `HttpTimeoutException` | Timeout under the `java.net.http.HttpClient` contract | Not a subclass of `SocketTimeoutException` |

The exception name is an **initial signal**. To handle it accurately, you must know which API was called, which step failed, and what might have happened on the peer side.

## 7. Connect Timeout: `Socket.connect(endpoint, timeout)`

One way to set an explicit connect timeout:

```java
try (Socket socket = new Socket()) {
    socket.connect(
            new InetSocketAddress(host, port),
            1500);
    // Use input/output streams only after connecting.
}
```

This is **illustrative code**, requiring imports for `java.net.Socket` and `java.net.InetSocketAddress`, as well as `host` and `port` in scope. The enclosing method must catch or declare the corresponding `IOException`.

The value `1500` is **1,500 milliseconds**, or 1.5 seconds as a parameter. It is the wait limit for the `connect` operation, not a guarantee that the method's total wall-clock time will never exceed 1.5 seconds across all DNS, scheduler, and network configurations.

Possible outcomes:

- Connection succeeds: `connect` returns normally.
- Timeout: may throw `SocketTimeoutException`.
- Endpoint refuses: may commonly throw `ConnectException`.
- No network route: may throw `NoRouteToHostException`.
- Other socket or I/O issues: may throw an appropriate `SocketException` or `IOException`.

**Note on resolution:** creating `InetSocketAddress(host, port)`, performing DNS lookup, and establishing the connection are separate phases to observe; this socket API should not be mistaken for a "whole-application deadline covering DNS, TLS, request, and response."

## 8. Java 17 Example: Error Classification Without Depending on the Internet

To get deterministic output when teaching **`catch` branches**, the following example *simulates* each exception type by instantiating it directly; it **does not generate real network errors**.

Save **`NetworkExceptionClassificationDemo.java`**:

```java
import java.io.IOException;
import java.net.ConnectException;
import java.net.NoRouteToHostException;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

public class NetworkExceptionClassificationDemo {
    static void classify(IOException error) {
        try {
            throw error;
        } catch (SocketTimeoutException e) {
            System.out.println("TIMEOUT");
        } catch (ConnectException e) {
            System.out.println("CONNECT_REFUSED");
        } catch (NoRouteToHostException e) {
            System.out.println("NO_ROUTE");
        } catch (SocketException e) {
            System.out.println("SOCKET_IO");
        } catch (UnknownHostException e) {
            System.out.println("DNS");
        } catch (IOException e) {
            System.out.println("OTHER_IO");
        }
    }

    public static void main(String[] args) {
        classify(new SocketTimeoutException("simulated"));
        classify(new ConnectException("simulated"));
        classify(new NoRouteToHostException("simulated"));
        classify(new SocketException("simulated"));
        classify(new UnknownHostException("simulated"));
        classify(new IOException("simulated"));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 NetworkExceptionClassificationDemo.java
java NetworkExceptionClassificationDemo
```

**Exact stdout:**

```text
TIMEOUT
CONNECT_REFUSED
NO_ROUTE
SOCKET_IO
DNS
OTHER_IO
```

Key learning points:

- `ConnectException` and `NoRouteToHostException` are subclasses of `SocketException`, so their specific handlers **must appear before** `catch (SocketException)`.
- `SocketTimeoutException` and `UnknownHostException` do **not** belong to the `SocketException` branch.
- The final `IOException` handles the remaining cases.
- You can reorder sibling `catch` blocks as long as it does not cause inheritance shadowing; the most important rule is **subclass before superclass**.

Do not rely on `error.getMessage()` for classification. When an application needs structured error codes, map them based on the exception type and **operation context**, not just the subtype.

## 9. `Socket.setSoTimeout(...)` Is for **Reading**, Not Connecting

For `java.net.Socket`, `setSoTimeout(int timeout)` configures the read wait limit on a blocking socket. Example:

```java
socket.setSoTimeout(500);
int next = socket.getInputStream().read();
```

This is **illustrative code**. If no data or EOF arrives before the wait limit, the read operation may throw `SocketTimeoutException`.

Notes to keep in mind:

- The value is in **milliseconds**.
- `0` means an **infinite timeout** for the associated wait operation (no active time limit enforced via `SO_TIMEOUT`).
- Negative values are invalid, and `setSoTimeout` throws `IllegalArgumentException`.
- `setSoTimeout` must be applied before the blocking operation you want to bound.
- `setSoTimeout` **does not replace** `Socket.connect(endpoint, connectTimeout)`.
- It does not create a deadline for the entire socket lifecycle or across successive reads.
- After a `read()` timeout, the socket itself normally remains valid, but **there is no guarantee that the application protocol is in a clean state** if a request was sent and only part of the response was received.

Do not use `InputStream.available() == 0` to assert that the remote peer has closed or that no more data exists; `available()` is only an estimate of bytes that can be read **without blocking**, not an EOF signal or connection-status indicator.

## 10. Self-Contained Example: Real Read Timeout on Loopback

This example uses **loopback** (`127.0.0.1` or the system's equivalent loopback address), requiring no external server or Internet access. It connects two socket ends within the **same process**, has the server side withhold sending any byte during the first read, and then sends a byte to verify that the client can continue reading after the timeout.

Save **`SocketReadTimeoutDemo.java`**:

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;

public class SocketReadTimeoutDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket server =
                     new ServerSocket(0, 50, loopback);
             Socket client =
                     new Socket(loopback, server.getLocalPort());
             Socket accepted = server.accept()) {

            client.setSoTimeout(150);
            InputStream input = client.getInputStream();

            try {
                input.read();
                throw new AssertionError("Expected read timeout");
            } catch (SocketTimeoutException e) {
                System.out.println("Read timed out");
            }

            accepted.getOutputStream().write(65);
            accepted.getOutputStream().flush();

            System.out.println("Byte after timeout: " + input.read());
            System.out.println("Client still open: " + !client.isClosed());
        }
    }
}
```

Compile/run with Java 17:

```bash
javac -encoding UTF-8 --release 17 SocketReadTimeoutDemo.java
java SocketReadTimeoutDemo
```

**Expected stdout on systems that allow TCP loopback**, assuming no external network interference on the ephemeral port:

```text
Read timed out
Byte after timeout: 65
Client still open: true
```

Explanation:

1. `new ServerSocket(0, 50, loopback)` opens an **ephemeral** port chosen by the operating system, bound specifically to loopback.
2. `client` connects to that port; `server.accept()` returns the server-side socket.
3. `client.setSoTimeout(150)` bounds each corresponding blocking read operation.
4. Because `accepted` has neither sent data nor closed its output, the first `input.read()` expires and throws `SocketTimeoutException`.
5. Then the server side sends **byte value 65**; the next `read()` returns `65`.
6. A read timeout **does not automatically `close()` the socket** in this example.

**This demonstrates real socket behavior**, not a hardcoded output guaranteed in environments that block loopback or have buggy JVMs/OSes. You should not assert exact elapsed milliseconds; the OS scheduler and machine load can affect when the exception fires. The port is chosen dynamically to avoid hardcoding a port.

## 11. Read Timeout Does Not Mean EOF

For an `InputStream` obtained from a TCP socket, a single-byte `read()` call typically has three outcome groups:

1. **A byte is read successfully:** `read()` returns a number in `0..255`.
2. **The stream ended cleanly with no more data:** `read()` returns `-1`.
3. **I/O failure or wait limit exceeded:** throws an appropriate `IOException`, which may be `SocketTimeoutException`.

If reading a byte returns `-1`, that is **not `SocketTimeoutException`** and should not be retried with the same logic as a timeout. It indicates EOF on the stream; in TCP, this is typically associated with the peer closing its sending output in an orderly manner.

For `read(byte[])`, the result also depends on the buffer length (requesting 0 bytes may return 0 immediately). When designing a protocol, you must read the exact number of bytes according to framing and distinguish incomplete data from EOF.

An exception such as `EOFException` can appear in structured reading APIs like `DataInputStream.readFully(...)` when a specific number of bytes is required but the stream ends prematurely. **The `-1` return value of `InputStream.read()` is not an `EOFException` object.**

## 12. Java 17 Example: Clean EOF Does Not Throw Timeout

Save **`SocketEndOfStreamDemo.java`**:

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class SocketEndOfStreamDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket server =
                     new ServerSocket(0, 50, loopback);
             Socket client =
                     new Socket(loopback, server.getLocalPort());
             Socket accepted = server.accept()) {

            client.setSoTimeout(1000);

            accepted.shutdownOutput();
            InputStream input = client.getInputStream();

            System.out.println("read after shutdownOutput: "
                    + input.read());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 SocketEndOfStreamDemo.java
java SocketEndOfStreamDemo
```

**Expected stdout when loopback works normally:**

```text
read after shutdownOutput: -1
```

`accepted.shutdownOutput()` performs a half-close in the **sending** direction from the server side. When the client reads and no data remains, it receives EOF (`-1`). This is an **orderly termination** rather than waiting until a timeout.

In real-world protocols, EOF can represent either **normal termination** or a **truncated response**, depending on framing. For example, if a protocol requires 100 bytes and the peer closes after 20 bytes, that is an incomplete-data error at the application layer, even though the stream-level signal is EOF.

## 13. `ServerSocket.accept()` Can Also Time Out

`ServerSocket` is the listening socket endpoint for TCP connections. If you need the server not to block forever in `accept()`, use:

```java
serverSocket.setSoTimeout(500);
Socket peer = serverSocket.accept();
```

This is **illustrative skeleton code**. `ServerSocket`'s timeout applies to **waiting for a new connection**; it does **not** automatically set a read timeout on the `Socket` returned by `accept()`.

When `accept()` exceeds the wait time, it throws `SocketTimeoutException`. Per the `ServerSocket` contract, **the `ServerSocket` remains valid** after the timeout; the program can continue waiting again, stop serving, or check a shutdown flag.

**You must close the accepted client socket yourself** when work with that client finishes, typically using try-with-resources or an appropriate connection-management mechanism. The listener timeout and the accepted connection's timeout are two separate policies.

## 14. Java 17 Example: Listener Times Out but Remains Open

Save **`ServerAcceptTimeoutDemo.java`**:

```java
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;

public class ServerAcceptTimeoutDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {

            server.setSoTimeout(120);

            try (Socket ignored = server.accept()) {
                System.out.println("Unexpected connection");
            } catch (SocketTimeoutException e) {
                System.out.println("Accept timed out");
            }

            System.out.println("Server still open: "
                    + !server.isClosed());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 ServerAcceptTimeoutDemo.java
java ServerAcceptTimeoutDemo
```

**Expected stdout in an environment where no client connects to the newly allocated loopback port:**

```text
Accept timed out
Server still open: true
```

The error occurred in `server.accept()`, not because the `ServerSocket` was closed. The system can continue calling `accept()` if that is its operational policy.

The example uses an ephemeral port and creates no threads or clients, making it ideal for verifying wait behavior. An environment that disallows opening a local listener may throw a bind/permission error before the timeout step; that is not the expected outcome of the example.

## 15. `DatagramSocket.receive()` and UDP Timeouts

UDP differs from TCP: there is no TCP connection guaranteeing delivery and byte-stream ordering in the same way. `DatagramSocket.receive(packet)` waits for a datagram to arrive at the socket; it can be configured with:

```java
datagramSocket.setSoTimeout(500);
datagramSocket.receive(packet);
```

This is **illustrative code**; it requires `DatagramSocket` and `DatagramPacket` variables. If no matching datagram arrives before the deadline, it may throw `SocketTimeoutException`.

Keep in mind:

- **A UDP timeout does not prove where a packet was lost**: the sender might not have sent anything, the packet might have been dropped, routing might have failed, or the timeout might simply be too short.
- A `DatagramSocket` can be logically connected to a peer, but UDP still has **no** TCP session like `Socket`.
- `PortUnreachableException` is a subclass of `SocketException`; on UDP it may relate to an ICMP port unreachable message, but **it is not guaranteed to appear on every OS or in every scenario**.
- Do not infer that a successful UDP `send` means the peer received or processed the data.
- If you need reliability, ordering, and retries, the application protocol must explicitly design them.

`DatagramSocket.setSoTimeout` only adjusts the receive wait operation; it is not a **complete deadline** for a custom retransmission mechanism.

## 16. Java 17 Example: UDP Receive Timeout on Loopback

Save **`DatagramTimeoutDemo.java`**:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;

public class DatagramTimeoutDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramSocket receiver =
                new DatagramSocket(0, InetAddress.getLoopbackAddress())) {

            receiver.setSoTimeout(120);

            byte[] data = new byte[32];
            DatagramPacket packet = new DatagramPacket(data, data.length);

            try {
                receiver.receive(packet);
                System.out.println("Packet received");
            } catch (SocketTimeoutException e) {
                System.out.println("UDP receive timed out");
            }
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 DatagramTimeoutDemo.java
java DatagramTimeoutDemo
```

**Expected stdout** when no actor sends a datagram to the newly allocated port:

```text
UDP receive timed out
```

There is no UDP-sending code in the program, so `receive` waits and then times out. If the environment forbids binding to loopback or an unexpected packet arrives at that port, the outcome branch may differ; real tests need stable network conditions.

The key takeaway is that **the same `SocketTimeoutException` type can appear in TCP read, `ServerSocket` accept, and UDP receive**, yet each place has a different operational meaning.

## 17. `ConnectException`: Connection Failed, Commonly Connection Refused

`ConnectException extends SocketException` and commonly occurs when a client tries to establish a connection to a port with no listening service, or when the endpoint refuses the connection according to OS behavior.

Skeleton code example:

```java
try (Socket socket = new Socket()) {
    socket.connect(
            new InetSocketAddress("127.0.0.1", 65000),
            500);
} catch (ConnectException e) {
    // Connection could not be established, typically because the endpoint refused it.
}
```

This is **illustrative code** with **no fixed stdout** and is **not a deterministic test**: port 65000 might still be in use on a particular machine. You must import `Socket`, `InetSocketAddress`, and `ConnectException`; other `IOException`s must also be handled or declared.

Do not look at a message like `"Connection refused"` and immediately assume the server process is not running. You also need to consider the IP/port, which interface the listener is bound to, firewalls, container/VM network namespaces, and network security policies.

If you want to genuinely test connection refusal, you must control the endpoint rather than guessing a port is "definitely free."

## 18. `BindException`: Unable to Bind the Local Endpoint

A server must bind to a local address/port before accepting connections. If the port is already occupied by another listener or the bind address is unavailable, `new ServerSocket(port)` or a bind operation can throw **`BindException`**, a subclass of `SocketException`.

Common misconceptions:

- **A bind failure** happens when preparing the **local-side** endpoint, not when a client reads a response.
- `BindException` can be caused by a port already in use, an address not present on the host, OS permissions, or network policies.
- You should not explain every `BindException` by saying "the remote server is dead."
- When a server binds to port `0`, the OS chooses an available port; you can read `serverSocket.getLocalPort()` after binding succeeds.

In the loopback examples in this article, port `0` is chosen to **minimize port collisions** and avoid assuming a fixed port is unused on a student's machine.

## 19. `UnknownHostException`: Name Resolution Failure, Not Connection Refused

`UnknownHostException extends IOException`, and **does not belong to `SocketException`**. It typically indicates that a hostname could not be resolved to an appropriate address via the active lookup mechanism.

Example:

```java
InetAddress resolved = InetAddress.getByName(hostName);
```

This is **illustrative code** with `hostName` in scope and `java.net.InetAddress` imported. If resolution cannot be performed, the API can throw `UnknownHostException`.

You should distinguish the phases:

1. **DNS/name resolution**: determining an address from a name.
2. **Connect**: attempting to establish a connection to the address/port.
3. **I/O**: sending and receiving data over the connection.
4. **Protocol/application**: receiving a syntactically and semantically valid response.

A failure in step 1 does not prove the host received and refused a connection in step 2. A successful connection in step 2 does not prove a business response will arrive in step 4.

**Do not rely on a fake hostname to create a DNS failure test with fixed stdout**: DNS has internal configurations, search domains, resolvers, or differing network environments. If you need to test classification logic, construct a synthetic `UnknownHostException` in a unit test as shown in `NetworkExceptionClassificationDemo`.

## 20. Socket Closed, Reset, and Broken Pipe

Common messages encountered when studying socket errors:

- `Socket closed`: the application attempted an operation on a socket that was already closed, or the resource was closed while an operation was waiting, depending on the API/implementation.
- `Connection reset`: the TCP connection was reset, which can be caused by the peer or a network component.
- `Broken pipe`: typically associated with a write operation when the other end is no longer accepting data according to OS state.

Note:

- **Messages are not an independent Java enum/contract.** Wording can vary by OS/JDK and operation step.
- A socket closed by the application's own code **is not proof of a network infrastructure failure**.
- `Socket.isClosed()` returning `false` does not guarantee the peer is alive or that the next I/O call will succeed.
- `Socket.isConnected()` reflects that the socket **has connected successfully at some point**, not a continuous health check confirming the peer is online.
- A successful `write` call on the client side does not by itself prove the server processed the request at the application layer.
- When a reset or broken pipe occurs, you must evaluate **whether the operation might have been partially executed** before retrying.

You should not replace all error messages with `SocketTimeoutException` or force them into a single "timeout" state.

## 21. How Does a Timeout Differ from a Slow-Responding Server?

If a `read()` operation receives no data within `SO_TIMEOUT`, Java can throw `SocketTimeoutException`. However, many causes can produce the exact same signal:

- The server is executing a slow query.
- The server received the request and is waiting on another dependency.
- The server is not sending a response because it is waiting for you to send more data per the protocol.
- Packets are delayed or dropped on the network.
- The peer crashed, but TCP has not yet delivered a close/reset signal observable by the receiver.
- The configured timeout is too short relative to normal latency.

Therefore, the statement "`SocketTimeoutException` proves the server did not process the request" is **false**. A timeout only confirms that **the caller's wait condition was exceeded**. The processing state at the peer may be **unknown**.

For operations with side effects, such as placing an order or transferring money, a timeout waiting for a response does not allow you to conclude the operation did not happen. You must have a request ID, idempotency, state lookup, or a compensation mechanism by design.

## 22. Retry Does Not Equal a Solution for Every `IOException`

When a `SocketTimeoutException`, `ConnectException`, or `SocketException` occurs, a good retry design must answer:

1. **At which step did the error occur?** Before sending the request, while sending, after sending, or while reading the response?
2. **Is the operation idempotent?** Reading data, an idempotent PUT state update, or a POST creating a new transaction?
3. **Might the server-side result already be committed?**
4. **Is there a maximum total time budget for all retries?**
5. **Is there a retry count limit and backoff/jitter?**
6. **Is there a token/idempotency key to handle repeated requests?**
7. **Is there a risk of creating a retry storm that overloads an already struggling system?**
8. **Is there a policy distinguishing misconfigured DNS or wrong addresses from transient errors?**

Safer examples:

- A **status-read** request can be retried within a bounded, designed policy.
- A **create-transaction** command may need an idempotency key and a transaction-status check before retrying.
- `UnknownHostException` due to a misconfigured domain name will likely not be fixed by continuous retries.
- `BindException` because a server port is already in use usually requires fixing configuration or freeing the port, not resending the same request multiple times.

Do not use pseudocode like `catch (IOException e) { retryForever(); }` as a default strategy.

## 23. Read Timeout Is Not an Overall Request Deadline

Suppose an application reads a long response across multiple `read()` calls, each with `SO_TIMEOUT = 2 seconds`. If the peer sends a small amount of data before each two-second interval elapses, the application can keep running **longer than two seconds in total**.

Therefore, you must distinguish:

- **Connect timeout**: time limit for establishing a connection in the connect API.
- **Read timeout / `SO_TIMEOUT`**: wait limit for a single applicable blocking read.
- **Accept timeout**: wait limit for a listener accepting a new connection.
- **Request deadline**: overall time limit for completing a task, designed by the application/framework layer.
- **Idle timeout**: inactivity time limit, which may be implemented at the server/proxy/framework layer.
- **TCP keepalive**: a mechanism for detecting dead peers over large configurable intervals; **not** a short request timeout.

Setting `setSoTimeout(2000)` **does not** replace an overall deadline. If there is a requirement that "the response must complete within 5 seconds," the system needs a deadline policy based on a monotonic clock, step budgets, and a corresponding cancellation/close mechanism when time expires.

## 24. `SocketTimeoutException` and `InterruptedIOException` Are Not `InterruptedException`

A subtle point of confusion: `SocketTimeoutException extends InterruptedIOException`, but that does **not** mean every timeout is caused by thread interruption.

- `InterruptedException` is a checked exception typically associated with a waiting task receiving an interrupt signal, such as `Thread.sleep()`.
- `InterruptedIOException` indicates an interrupted I/O operation and has a `bytesTransferred` field for certain contexts.
- `SocketTimeoutException` is a subclass of `InterruptedIOException` used to report that a socket operation **timed out**.
- **Do not call `Thread.currentThread().interrupt()` just because you caught `SocketTimeoutException`.** A timeout does not prove the thread received a cancellation request.

In some other I/O and channel APIs, thread interruption can lead to specialized exceptions, such as `java.nio.channels.ClosedByInterruptException`. Do not force everything into `SocketTimeoutException`; handle exceptions according to the contract of the API actually in use.

The `InterruptedIOException.bytesTransferred` field should not be treated as "the total bytes of the entire request successfully delivered to the server" in every situation. If a protocol requires exact confirmation, use application-layer acknowledgments and state.

## 25. TCP Client Skeleton with Timeouts and Resource Closing

This is an **illustrative method**, syntactically valid Java without a server or `main`, so it has no fixed stdout. It demonstrates configuring **connect timeout** separately from **read timeout**, and managing the socket with try-with-resources:

```java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;

class SimpleTcpClient {
    static int readOneByte(String host, int port) throws IOException {
        try (Socket socket = new Socket()) {
            socket.connect(
                    new InetSocketAddress(host, port),
                    1500);
            socket.setSoTimeout(2000);
            return socket.getInputStream().read();
        }
    }
}
```

Meaning:

1. `new Socket()` creates an unconnected socket.
2. `connect(..., 1500)` applies a dedicated timeout to TCP connection setup.
3. `setSoTimeout(2000)` limits the wait on the subsequent blocking read.
4. `read()` returns a byte, `-1` on EOF, or throws an I/O/timeout error.
5. `try-with-resources` automatically calls `close()` on normal exit or exception.

**Do not use this as a complete protocol client**: it does not build requests, verify framing, read long responses, enforce an overall task deadline, or implement a retry policy.

If a real method needs to return "no data," returning `-1` can preserve the `InputStream` contract; the caller layer must understand that `-1` differs from a timeout.

## 26. Handle Exceptions by Type at the Responsible Boundary

An error-control pattern might look like this:

```java
try {
    performNetworkOperation();
} catch (SocketTimeoutException e) {
    handleTimeout(e);
} catch (UnknownHostException e) {
    handleNameResolutionFailure(e);
} catch (ConnectException e) {
    handleConnectFailure(e);
} catch (SocketException e) {
    handleOtherSocketFailure(e);
} catch (IOException e) {
    handleOtherIoFailure(e);
}
```

This is **illustrative skeleton code** with handler methods to be defined and appropriate `java.io.*` and `java.net.*` imports. Order matters:

- `ConnectException` must come before `SocketException`.
- `SocketTimeoutException` and `UnknownHostException` are not under `SocketException`.
- `IOException` comes last as the common superclass.

However, **not every layer should catch all six branches**. If a repository layer has no way to recover, it can declare `throws IOException`; the API/job layer that has request context, policies, and response capability will handle it.

A handler must distinguish between **genuinely recovering** and **turning an error into a failure response**. Catching to log and then returning dummy data is a bug if the caller thinks the operation succeeded.

## 27. Structured Logging: Record the Exception, Not Just the Message

For network errors, printing only `e.getMessage()` is usually insufficient because:

- The message can vary by JVM/OS.
- It does not tell you the exact exception type.
- It does not always show the cause or suppressed exceptions.
- There is no stack trace when you only store a `String`.
- There is no operation context: connect, read, write, accept, or DNS.
- There is no request ID or configured timeout information.

A useful log entry should include **the allowed address/endpoint, operation name, configured timeout, attempt number, request correlation ID, exception type, and the original `Throwable`**.

Pseudocode for a logging library with an overload that accepts a `Throwable`:

```java
// Pseudocode; signature depends on the logging framework in use:
logger.error("Network operation failed: requestId={}, phase={}",
             requestId, phase, exception);
```

This is **not** compilable standalone Java code without a logger and variables. The goal is to emphasize: pass the **exception object** when the framework supports it, so stack trace/cause/suppressed exceptions are preserved.

Do not put access tokens, cookies, passwords, sensitive query strings, or personal payloads into logs just to add context.

## 28. Wrapping Errors with `cause` When Crossing Abstraction Boundaries

A business API might not want to expose `IOException` directly and may use a custom exception instead:

```java
class NetworkOperationException extends RuntimeException {
    NetworkOperationException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Call example:

```java
try {
    sendRequest();
} catch (IOException e) {
    throw new NetworkOperationException(
            "Unable to execute request", e);
}
```

Both are **illustrative snippets**, requiring `sendRequest()` and `IOException` in scope, with no fixed stdout.

When wrapping:

- The wrapper exception carries the **type and message of the new layer**.
- `wrapper.getCause()` retains the `IOException` object, including `SocketTimeoutException` or `ConnectException`.
- The wrapper's stack trace is recorded where the wrapper is created; the cause retains its own trace.
- Any suppressed exceptions attached to the cause are **not automatically copied** to `wrapper.getSuppressed()`.
- API callers now see unchecked `NetworkOperationException` instead of checked `IOException`.

**Do not wrap using only `new RuntimeException(e.getMessage())` if you need to preserve the cause.** Choosing checked vs. unchecked for a wrapper should be an API contract decision, not merely a way to avoid writing `throws`.

## 29. Java 17 Example: Preserving `cause` from a Timeout

This example **simulates a timeout** so the output does not depend on the network environment; it focuses on wrapping and `cause`.

Save **`NetworkCauseDemo.java`**:

```java
import java.io.IOException;
import java.net.SocketTimeoutException;

public class NetworkCauseDemo {
    static class ServiceNetworkException extends RuntimeException {
        ServiceNetworkException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void lowLevelRead() throws IOException {
        throw new SocketTimeoutException("read timed out");
    }

    static void fetch() {
        try {
            lowLevelRead();
        } catch (IOException e) {
            throw new ServiceNetworkException("Fetch failed", e);
        }
    }

    public static void main(String[] args) {
        try {
            fetch();
        } catch (ServiceNetworkException e) {
            System.out.println("Wrapper: " + e.getMessage());
            System.out.println("Cause class: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
            System.out.println("Cause is IOException: "
                    + (e.getCause() instanceof IOException));
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 NetworkCauseDemo.java
java NetworkCauseDemo
```

**Exact stdout:**

```text
Wrapper: Fetch failed
Cause class: SocketTimeoutException
Cause message: read timed out
Cause is IOException: true
```

`ServiceNetworkException` is a new application exception type. `getCause()` still retains `SocketTimeoutException` and its original message. In a real system, deciding whether to retry requires **context**, not just checking whether the cause is `SocketTimeoutException`.

If a network error has been wrapped multiple times, the handling layer may need to traverse the cause chain carefully (avoiding cycles in case of non-standard custom exception structures).

## 30. Try-With-Resources and Errors When Closing Sockets

Both `Socket` and `ServerSocket` implement `AutoCloseable`, so you can use:

```java
try (Socket socket = new Socket()) {
    // connect, read, write...
}
```

This is **illustrative skeleton code**. When leaving the scope, Java attempts to close the socket. If the primary operation threw an exception and `close()` also throws an exception, Java can attach the closing error to the **suppressed exceptions** of the primary error via the try-with-resources mechanism.

Consequences:

- During diagnosis, you may need to inspect `primary.getSuppressed()` to see whether cleanup also failed.
- `getCause()` and `getSuppressed()` are not the same thing.
- Do not swallow cleanup errors just to make logs look cleaner.
- When a socket is no longer usable, closing the resource and creating a new connection per contract may be better than trying to reuse the old object.
- A `SocketTimeoutException` caused by **read `SO_TIMEOUT`** does not by itself guarantee the socket is broken or closed, though the application layer must still manage protocol conditions.

Do not assume that just because a socket is in a try-with-resources block, all application data was acknowledged by the server or all side effects were rolled back.

## 31. What You Cannot Infer from `Socket` State

Several methods have names that can mislead readers into thinking they check "connection health":

- `socket.isConnected()`: indicates whether the socket was ever connected successfully, **not** a continuous probe confirming the peer is still alive.
- `socket.isClosed()`: checks whether the socket object has been closed on the local side.
- `socket.isInputShutdown()` / `isOutputShutdown()`: local-side shutdown state of each direction.
- `input.available()`: estimate of bytes readable without blocking, **not** used to determine EOF or whether the remote side finished sending.
- `socket.getSoTimeout()`: reads the configured read timeout, **not** the overall deadline or remaining time of a request.

If you need a **health check**, you should have a protocol-level mechanism: appropriate ping/pong, a health-check request, heartbeats, or verifying actual I/O results—while still accepting that networks have latency and failures.

No synchronous API can guarantee that peer state **will still be valid** at the moment of the next operation in a distributed system.

## 32. Distinguishing from Java NIO and Java HTTP Client

### 32.1. Java NIO Channels

`java.nio.channels.SocketChannel` and other channels have their own I/O APIs; depending on the situation, exceptions such as these may appear:

- `ClosedChannelException`,
- `AsynchronousCloseException`,
- `ClosedByInterruptException`,
- appropriate `IOException`s.

**Do not assume `Socket.setSoTimeout` controls all non-blocking NIO or selector operations**. In NIO designs, timeouts are typically managed via selectors, deadlines, or appropriate higher-level APIs. Check the specific contract of the channel and its blocking/non-blocking mode.

### 32.2. `java.net.http.HttpClient`

Java 11+ includes the standard HTTP client `java.net.http.HttpClient`. Timeouts in this API have specialized exceptions:

- `java.net.http.HttpTimeoutException`: in the `IOException` branch.
- `java.net.http.HttpConnectTimeoutException`: a subclass of `HttpTimeoutException`, used in the context of HTTP Client connect timeouts.

These types are **not `SocketTimeoutException`**. If you are using `HttpClient`, you must rely on **the HTTP Client's API and exception types**, rather than applying `catch` blocks written for classic `Socket` to all HTTP calls.

Other HTTP libraries have their own wrappers, retries, and async exceptions; the library's documentation always matters more than guessing from raw socket classes.

## 33. TLS/SSL Errors Are a Different Layer

When using `SSLSocket` or HTTPS, there is an additional **TLS handshake**, certificate verification, and encryption protocol. Exceptions that may appear include `javax.net.ssl.SSLException` and its subclasses, along with lower-level socket/I/O errors.

Do not conclude:

- Having an `SSLException` means DNS is wrong.
- Having a `SocketTimeoutException` means the TLS certificate is invalid.
- A successful TCP connect guarantees the TLS handshake will succeed.
- A TCP read timeout equals a timeout for the entire handshake and HTTP response in every API.

In real systems, each layer should record context: **resolve -> connect -> TLS handshake -> write request -> read response -> parse**. This helps distinguish configuration errors, network errors, and protocol errors.

If your goal is simply to understand `SocketException`/`SocketTimeoutException` in core Java, treat TLS/HTTP as **additional layers** and do not confuse their exceptions with all forms of socket errors.

## 34. Do Not Rely on OS Error Messages in Tests

A test like:

```java
assertEquals("Connection refused", exception.getMessage());
```

is an **illustrative anti-pattern** (assuming an assertion framework). Messages can differ across Linux, Windows, JDKs, and contexts. More stable checks include:

- The appropriate exception type or superclass.
- A **domain-layer** error code if the application defines its own.
- The wrapper's `cause` when crossing abstraction boundaries.
- The number of retries or fallback policy executed.
- Resource state after failure.
- Timeout bounds at the contract level, avoiding assertions on exact wall-clock numbers.

When you want to test error classification, you can **create synthetic exceptions** like `new ConnectException("simulated")`. When you need socket integration tests, use **loopback and ephemeral ports** to reduce network dependencies, while still documenting environment assumptions.

## 35. Testing Timeouts and Avoiding Flaky Tests

Timeout tests can easily become unstable if they depend on the OS scheduler or machine load. Ways to reduce risk:

1. Separate **unit tests of logic** from **integration tests that actually create sockets**.
2. Unit test with synthetic exceptions when checking classification/retry policies.
3. For real sockets, use **loopback** and `ServerSocket(0)` instead of Internet services or fixed ports.
4. Do not assert `elapsedMillis == configuredTimeout`; real execution has overhead.
5. Do not sleep blindly waiting for a thread that may not have started; use `CountDownLatch` or synchronization primitives when threads are needed.
6. Do not turn a timeout test into a deadlock where client and server wait on each other due to a broken protocol.
7. Ensure resources are closed in `try-with-resources`, even when a test fails.
8. Avoid "ports definitely unused by anyone"; ports are always subject to races and environment configuration.
9. If you need to test retries, use a mock/fake server controlling request IDs and response behavior rather than relying on random Internet failures.
10. Allow reasonable timeouts for CI and document that tests require loopback bind/connect capability.

**Real socket tests reflect runtime/network behavior; synthetic unit tests reflect classification code.** Both are valuable, but they should not be confused conceptually.

## 36. Common Mistakes

| Misconception | Correct understanding |
| --- | --- |
| "`SocketTimeoutException extends SocketException`." | False. It extends `InterruptedIOException`, whereas `SocketException` extends `IOException` directly. |
| "Catching `SocketException` catches all timeouts." | False. You must catch `SocketTimeoutException` or an appropriate `IOException`. |
| "`ConnectException` is a separate branch outside `SocketException`." | False. `ConnectException` is a subclass of `SocketException`. |
| "`UnknownHostException` is a subclass of `SocketException`." | False. It belongs to `IOException`, not under `SocketException`. |
| "A timeout means the server definitely did not process the request." | False. The operation may have been processed while the response did not arrive. |
| "A read timeout is a deadline for the entire request." | False. `SO_TIMEOUT` applies to blocking read operations, not automatically to the whole workflow. |
| "`setSoTimeout` sets the `connect` timeout." | False. Use `connect(endpoint, timeout)` for connecting. |
| "`SocketTimeoutException` always closes the socket." | False. A read timeout on a blocking socket does not automatically close the socket. |
| "`Socket.isConnected() == true` means the peer is online." | No. It is not a real-time health check. |
| "`available() == 0` means EOF." | False. It does not prove the peer closed or the stream ended. |
| "`read() == -1` means timeout." | False. `-1` is EOF, distinct from a timeout exception. |
| "Socket reset and socket closed are both DNS errors." | False. You must examine timing, error type, and operation. |
| "A successful UDP send guarantees data was received." | False. UDP provides no such guarantee by default. |
| "Every timeout should be retried immediately forever." | False. You need limits, backoff, idempotency, and an overall deadline. |
| "A read timeout means you must call `Thread.interrupt()`." | False. A timeout is not a thread `InterruptedException`. |
| "The `Connection reset` message can be used as a stable error code." | No. Messages depend on runtime/OS and context. |
| "Java HTTP Client timeouts always throw `SocketTimeoutException`." | No. `java.net.http` has `HttpTimeoutException`/`HttpConnectTimeoutException`. |
| "Logging only the message is enough to investigate socket errors." | Usually not; you need the `Throwable`, cause, and context. |
| "Catching `IOException` and returning success makes the app more resilient." | False if not properly recovered; that can be a false success. |
| "Using try-with-resources means the server processed the transaction safely." | No. It manages closing resources, not confirming side effects on the peer. |

## 37. Self-Check Questions

**1.** Is `SocketException` checked?  
**Answer:** Yes, because it extends `IOException`.

**2.** Is `SocketTimeoutException` a subclass of `SocketException`?  
**Answer:** No. It is a subclass of `InterruptedIOException`, which also extends `IOException`.

**3.** Does catching `SocketException` catch `ConnectException`?  
**Answer:** Yes, because `ConnectException extends SocketException`.

**4.** Does catching `SocketException` catch `UnknownHostException`?  
**Answer:** No. `UnknownHostException` is under `IOException` on a different branch.

**5.** Which API sets the connect timeout for a classic `Socket`?  
**Answer:** `socket.connect(endpoint, timeoutMillis)`.

**6.** Which API limits how long `Socket.getInputStream().read()` waits?  
**Answer:** `socket.setSoTimeout(timeoutMillis)` before the applicable blocking read.

**7.** Which operation does `ServerSocket.setSoTimeout` affect?  
**Answer:** How long `ServerSocket.accept()` waits for a new connection.

**8.** Which operation is `DatagramSocket.setSoTimeout` used with?  
**Answer:** `DatagramSocket.receive(...)`.

**9.** After a read timeout, is the socket definitely closed?  
**Answer:** No. A read timeout does not automatically force-close the socket; the application must decide whether to continue or close per the protocol.

**10.** How does `InputStream.read()` returning `-1` differ from `SocketTimeoutException`?  
**Answer:** `-1` is EOF; a timeout is an exception thrown when the applicable wait time expires.

**11.** Which phase is `ConnectException` typically associated with?  
**Answer:** Connection establishment, commonly when the endpoint refuses or cannot establish the connection via the OS mechanism.

**12.** Does `BindException` happen when a client reads data or when preparing a local endpoint?  
**Answer:** Primarily during the local endpoint bind operation.

**13.** Is a DNS/name resolution failure necessarily a `SocketException`?  
**Answer:** No. `UnknownHostException` is a separate subclass of `IOException`.

**14.** Does `setSoTimeout(0)` mean "timeout immediately"?  
**Answer:** No. `0` means no `SO_TIMEOUT` wait limit is set for the associated operation.

**15.** If the server already processed a create-transaction command but the client times out waiting for the response, can you retry unconditionally?  
**Answer:** No. You need an idempotency key, status checks, and a bounded retry policy.

**16.** Is `Socket.isConnected()` a current peer health check?  
**Answer:** No. It reflects that the socket was connected at some point, not that the peer is still serving.

**17.** Why shouldn't `InputStream.available() == 0` be used to conclude EOF?  
**Answer:** It only reports an estimate of bytes readable without blocking; data might not have arrived yet even though the stream has not ended.

**18.** Does `SocketTimeoutException` extending `InterruptedIOException` mean the thread must have been interrupted?  
**Answer:** No. A timeout is a wait condition and does not prove the thread received an interrupt signal.

**19.** When Java HTTP Client times out, which types may be involved?  
**Answer:** `HttpTimeoutException` and `HttpConnectTimeoutException` under the `java.net.http` contract, not `SocketTimeoutException` by default.

**20.** Why should you pass `cause` (accessed via `getCause()`) when wrapping network errors into domain exceptions?  
**Answer:** To preserve the original exception, error type, and stack trace, avoiding information loss when changing abstractions.

**21.** Two `read()` calls each receive data before their individual read timeouts, yet total time exceeds the business deadline. Will `SO_TIMEOUT` automatically stop the request?  
**Answer:** Not necessarily. You need an overall deadline at the application layer.

**22.** When debugging a network error, is knowing only the `"Broken pipe"` message enough?  
**Answer:** No. You need the operation being called, connection state, cause, OS/JDK, and business outcome.

**23.** Why is testing a connection to a "definitely free" port unreliable?  
**Answer:** Another process can use the port, creating races and differences across environments.

**24.** Can you use loopback to self-study timeouts without Internet access?  
**Answer:** Yes, with `ServerSocket(0)` and `Socket` in the same process, if the system permits TCP loopback.

## 38. Network Error-Handling Checklist

Before designing or reviewing a Java networking call:

1. **Identify the API in use:** classic `Socket`, `ServerSocket`, `DatagramSocket`, NIO, or HTTP Client.
2. **Know the exception hierarchy:** `SocketTimeoutException` is not under `SocketException`.
3. **Note the exact phase:** resolve, bind, connect, TLS, write, read, accept, or receive.
4. **Distinguish timeout from EOF:** `read() == -1` is not `SocketTimeoutException`.
5. **Set connect timeout if needed:** via `connect(endpoint, timeout)`.
6. **Set read timeout separately:** via `Socket.setSoTimeout` when using classic blocking sockets.
7. **Set accept timeout separately for listeners:** via `ServerSocket.setSoTimeout` when appropriate.
8. **Remember a timeout is not an overall deadline:** design a request budget/deadline if needed.
9. **Do not use `isConnected()` or `available()` as an infallible health check.**
10. **Evaluate idempotency before retrying:** the request may already have executed on the server.
11. **Bound retries and use reasonable backoff/jitter.**
12. **Keep request IDs/correlation IDs and server state** to disambiguate unknown outcomes.
13. **Do not swallow exceptions and return false success.**
14. **When wrapping, pass the cause:** `new XxxException(message, cause)`.
15. **Use try-with-resources** to close sockets according to their lifecycle.
16. **Inspect suppressed exceptions** if both the primary operation and cleanup fail.
17. **Do not classify errors solely by OS/JDK message strings.**
18. **Avoid logging credentials, tokens, or sensitive queries/payloads.**
19. **Distinguish UDP from TCP:** do not assume UDP has delivery confirmation.
20. **Handle thread interruption separately** from socket timeouts.
21. **Write network-independent unit tests for error types**, and separate loopback integration tests.
22. **Do not assert exact wall-clock wait times in tests.**
23. **If using `HttpClient`/NIO, read their separate contracts**, rather than mechanically applying old `Socket` rules.
24. **Review concurrency scenarios:** a socket can be closed by another thread; state checks do not eliminate races.
25. **Expose failures at the right boundary:** APIs should handle or declare checked exceptions according to each layer's responsibility.

## 39. Conclusion

`SocketException` and `SocketTimeoutException` both belong to the checked `IOException` family, yet **they sit on different branches and carry different meanings**. `SocketException` represents a general group of socket errors and includes subclasses such as `ConnectException`, `BindException`, and `NoRouteToHostException`. `SocketTimeoutException` extends `InterruptedIOException` and signals that a socket operation waited past its configured time limit; **`catch (SocketException)` does not catch it**.

In practical TCP/UDP programming, set timeouts at the right layer: **connect timeout** for connecting, and **`SO_TIMEOUT`** for reading, receiving, or accepting as appropriate; distinguish **EOF (`-1`)** from timeouts, and do not treat OS messages as stable error codes. Socket reading and writing also depend on the protocol, resource state, and the possibility that a request already caused side effects on the server.

Good error-handling design does not stop at catching the right type: it requires **overall deadlines, idempotency, bounded retries, context-rich logging, cause preservation, resource management, and testing that separates error-handling logic from the network environment**. This is the foundation for using Java networking safely and diagnosing incidents reliably.
