# Building a TCP echo client/server on loopback with an OS-assigned port

## 1. Objectives and deliverables of this lab

This lab uses **Java 17+**, the standard `java.net` library, and **TCP** connections to build an **echo server** (a server that returns the data it receives) along with an **echo client** on a single machine. The server listens only on **IPv4 loopback `127.0.0.1`** and asks the operating system to assign an **ephemeral port** by binding to port `0`. The client does not know the port number in advance: it retrieves the **actual port from `ServerSocket.getLocalPort()`**, then connects, sends data, and verifies the exact echoed data.

Specific learning outcomes:

1. Understand how **`ServerSocket` differs from `Socket`**; know how to bind, accept, connect, and read/write streams on the appropriate side.
2. Create a server **without hard-coding a port**, avoiding port conflicts when multiple tests run in parallel; connect using the same IPv4 loopback and the newly assigned port.
3. Build a protocol where **each UTF-8 line is one message**: the client sends three lines, and the server receives them and returns `ECHO:...`.
4. Use `flush()`, `Socket.shutdownOutput()`, and a read loop until **EOF** to end the echo session in an orderly manner without hanging while both sides wait on each other.
5. Use `InputStream` and `OutputStream` to echo **binary bytes**, explaining why one `read(byte[])` call **does not correspond** to one `write(byte[])` call.
6. Apply connect/read/accept timeouts, `try-with-resources`, and worker thread cleanup, while distinguishing loopback examples from production networked systems that require real security.

Two standalone runnable programs in this lab:

- `TcpEchoLinesDemo.java`: echoes three Unicode text lines, demonstrating OS-assigned port `0` and EOF on half-close.
- `TcpEchoBytesDemo.java`: echoes seven raw bytes, including `0x00` and `0xFF`, using a small buffer to prove that you must handle the exact number of bytes read on each call.

Both programs **launch the server and client themselves within the same JVM**, requiring no Internet connection and no frameworks or libraries outside the JDK. They are designed for **one client per run**, not as a production TCP service.

## 2. Data flow diagram

~~~text
                     same machine / IPv4 loopback
                  127.0.0.1 (no Internet access)

 SERVER                                      CLIENT
 ServerSocket(port=0)                        Socket()
      |                                         |
      | OS assigns actual port P > 0            |
      |                                         |
      |<----- connect(127.0.0.1:P) --------------|
      | accept() returns peer Socket            |
      |                                         |
      |<------- bytes / lines -------------------|
      | read via peer.getInputStream()          |
      |                                         |
      |------- echo bytes / lines -------------> |
      | write via peer.getOutputStream()        |
      |                                         |
      |<------- FIN on client.shutdownOutput() --|
      | sees EOF on client -> server direction  |
      | closes peer Socket after echoing        |
      |                                         |
      |--------- EOF server -> client ---------> |
      |                                         |
      +---- server.close()                       +-- client.close()
~~~

**`ServerSocket` is a listening socket**: it accepts new connections via `accept()`; it is not used directly to read the body of a connection. **The `Socket` returned by `accept()`** is the socket used to read/write the TCP exchange of the connected client. On the client side, a separate `Socket` object calls `connect(...)` to the bound address.

**TCP is a bidirectional (full-duplex) byte stream**, not a protocol with built-in "messages" or "lines". The lab's echo server explicitly defines **message boundaries** using a newline in demo 1 or waiting for EOF in demo 2; that is an **application** convention, not something TCP knows on its own.

## 3. Required APIs and their exact roles

| Java API | Which side | Meaning |
| --- | --- | --- |
| `new ServerSocket(0, backlog, bindAddress)` | Server | Creates and binds the address; port `0` lets the OS choose |
| `new ServerSocket()` + `bind(endpoint, backlog)` | Server | Creates unbound, then binds explicitly |
| `ServerSocket.getLocalPort()` | Server | Gets the **actual port after binding** |
| `ServerSocket.getInetAddress()` | Server | Gets the local address the server bound to |
| `ServerSocket.accept()` | Server | Waits for a connection; returns a connected `Socket` |
| `ServerSocket.setSoTimeout(ms)` | Server | Limits **how long `accept()` waits** |
| `new Socket()` + `connect(addr, timeout)` | Client | Opens a TCP connection to IP/port, with a connect timeout |
| `Socket.getInputStream()` | Both | Reads bytes from the peer |
| `Socket.getOutputStream()` | Both | Sends bytes to the peer |
| `Socket.setSoTimeout(ms)` | Both | Limits **how long a read waits** (`read`) |
| `Socket.shutdownOutput()` | Client in demo | Signals the end of the **send direction**, while still allowing reads on the receive direction |
| `Socket.close()` | Both | Releases the socket and closes associated streams |
| `BufferedReader.readLine()` | Text protocol | Reads up to newline/EOF, returning `null` at the end of the stream |
| `InputStream.read(byte[])` | Binary protocol | Reads **at most** the buffer capacity, returning the actual bytes read or `-1` at EOF |

`java.net.ServerSocket` and `java.net.Socket` belong to **`java.base`**, built into JDK 17, with no external dependencies required. UTF-8 encoding uses `java.nio.charset.StandardCharsets.UTF_8` to avoid depending on the environment's default charset.

## 4. Port 0: asking the OS to pick a port, not having the client connect to port 0

The clearest way to bind for a test:

~~~java
try (ServerSocket listener = new ServerSocket(
        0, 16, InetAddress.getByName("127.0.0.1"))) {
    int port = listener.getLocalPort(); // > 0 after binding succeeds
    System.out.println("port > 0: " + (port > 0));
}
~~~

*This illustrative snippet requires imports; it is not yet a complete echo program.*

With `new ServerSocket(0, 16, bindAddr)`:

- `0` is a **binding parameter**, telling the operating system "pick an available local port." It is **not the port the client should use**.
- `16` is the requested **backlog** (the queue of connections waiting for `accept`), **not** the number of concurrently handled requests, nor is the OS guaranteed to use that exact number.
- `InetAddress.getByName("127.0.0.1")` specifies **IPv4 loopback**: the server listens only on this local address rather than all interfaces.
- `listener.getLocalPort()` returns the assigned port; the specific value **cannot be predicted and may differ on every run**.

An equivalent approach is to create an unbound server:

~~~java
try (ServerSocket listener = new ServerSocket()) {
    listener.bind(new InetSocketAddress("127.0.0.1", 0), 16);
    int port = listener.getLocalPort();
}
~~~

Here `new ServerSocket()` initially has no address; `bind(...)` attaches the socket to loopback and an OS-assigned port. Once bound, do not call `bind(...)` a second time on the same `ServerSocket`.

**Do not open a temporary socket to grab a "free port", close it, and then reopen the server on that port.** In the gap between those two actions, another process can claim the port (*time-of-check vs time-of-use race*). The right approach is to keep **the very `ServerSocket` bound to port `0`** and pass `getLocalPort()` to the client while the listener remains open.

## 5. Loopback `127.0.0.1` vs `localhost` and `0.0.0.0`

| Value | Meaning | Choice for this test |
| --- | --- | --- |
| `127.0.0.1` | IPv4 loopback of the current machine | **Use for both server and client** |
| `localhost` | Hostname, may resolve to IPv4 or IPv6 | Valid, but can cause address-family mismatches depending on the environment |
| `::1` | IPv6 loopback | Use only if both server and client use IPv6, with appropriate URI syntax |
| `0.0.0.0` | Bind **all IPv4 interfaces** | Do not use for demos unless there is a reason to expose external network access |
| LAN IP | Bind an interface outside loopback | Requires appropriate firewall, auth, and permission policies |

When a server binds `127.0.0.1`, connections must go to the corresponding loopback address; do not assume clients from other machines can reach it. Inside a container, `127.0.0.1` is the loopback **of that network namespace**, not necessarily that of the host or another container.

The demos use **the same `"127.0.0.1"` string on both ends**, avoiding a setup where `localhost` resolves to `::1` while the server only binds IPv4. `InetAddress.getLoopbackAddress()` can also return different loopback types depending on the platform; choosing IPv4 explicitly keeps the lab reproducible.

## 6. When does `accept()` start accepting connections?

The server must **finish binding before the client calls `connect`**. After binding, the socket is listening, but `accept()` normally **blocks the calling thread** until a connection arrives.

~~~java
ServerSocket listener = new ServerSocket(
        0, 16, InetAddress.getByName("127.0.0.1"));
listener.setSoTimeout(5_000);

Socket peer = listener.accept(); // Wait for client to connect.
~~~

*This illustrative snippet assumes imports; both `listener` and `peer` must be closed at the end.*

Each successful `accept()` returns a **Socket for that connection**, distinct from the listening `ServerSocket`. To serve multiple clients, you typically write an `accept()` loop and hand each socket to an executor or I/O event loop; this lab serves only **one** client so the flow is easy to observe.

Never run sequentially as "call `accept()` and then run `connect()` on **the same thread**", because `accept()` will block forever waiting for a client that is never initiated. Both programs use a separate worker thread via `ExecutorService` for the server and the main thread for the client. There is no need to call `Thread.sleep(...)`: when the worker is created, the listener is **already bound**, so the client can connect even if the server has not yet entered `accept()`; the OS can place the connection in the pending queue.

`listener.setSoTimeout(5_000)` causes `accept()` to throw `SocketTimeoutException` if no connection arrives within the limit. Timing out **does not automatically close the `ServerSocket`**; if it wants to keep listening, the server must decide to call `accept()` again. The demos close the listener via `try-with-resources` after running.

## 7. Client connects to the exact OS-assigned port

On the client side:

~~~java
try (Socket client = new Socket()) {
    client.connect(new InetSocketAddress(
            "127.0.0.1", listener.getLocalPort()), 3_000);
    client.setSoTimeout(5_000);
    // client.getInputStream(), client.getOutputStream()
}
~~~

*This illustrative snippet uses the `listener` variable from the server side in the same JVM and requires imports.*

`client.connect(..., 3_000)` sets the timeout for **the connect operation**, which is separate from the read timeout. `client.setSoTimeout(5_000)` specifies that when a read operation on the socket waits too long for data, it throws `SocketTimeoutException`; this is **not a lifetime timeout**, does not cap the total number of bytes to read, and does not automatically set a deadline on every write.

Mistakes to avoid:

- Client connecting to port **`0`**: wrong. Port `0` only has meaning for **the server to bind and ask the OS for a port**, not as a real serving endpoint.
- Client hard-coding port `8080` while the server bound port `0`: the two sides use **two different ports**.
- Client using `localhost` resolving to IPv6 while the server listens on IPv4 `127.0.0.1`: may encounter `ConnectException`.
- Calling `client.getInputStream().read()` before the server has data without a protocol/timeouts: may block indefinitely.
- Believing that a successful `connect()` proves a business application has received the request: it only proves the TCP connection has been established.

## 8. Text echo: defining framing yourself with newlines and UTF-8

TCP **only transmits an ordered stream of bytes**; it does not provide an API to "receive exactly one message" per `write`. Because the demo wants to echo text lines, we define an application protocol:

~~~text
CLIENT SENDS, UTF-8:
xin chào\n
TCP Java 17\n
line=3\n
[FIN: shutdownOutput()]

SERVER RETURNS, UTF-8:
ECHO:xin chào\n
ECHO:TCP Java 17\n
ECHO:line=3\n
[EOF when server closes Socket]
~~~

The `\n` sequences in the diagram represent **newline characters**, not that the server is guaranteed to receive one `read()` per line. Java's `BufferedReader.readLine()` reads data until a line terminator or EOF and strips the delimiter; it returns **`null`** when the end of the input stream is reached.

Combine:

- `new InputStreamReader(socket.getInputStream(), UTF_8)` to decode bytes into characters.
- `new BufferedReader(...)` and `readLine()` to receive each line according to the framing.
- `new OutputStreamWriter(socket.getOutputStream(), UTF_8)` to encode text into UTF-8.
- `new BufferedWriter(...)`, `write(...)`, `newLine()`, and `flush()` to send buffered lines.

**`flush()` is critical** with buffered output: bytes may still be sitting in `BufferedWriter`'s buffer without being forwarded to the socket. If the server is waiting for a newline while the client has not flushed, both sides can end up waiting on each other.

**Limitations of a line protocol:** payloads should not contain unescaped newlines; encoding must match on both ends; `readLine()` does not automatically limit the number of characters in a line. With untrusted user data, production systems need limits on individual frame/line length, charset decoding, and total bytes. The demo only sends three small predefined lines.

## 9. Java 17+ program #1: echoing three Unicode lines over loopback

Create the file **`TcpEchoLinesDemo.java`**. The program opens `ServerSocket(0,16,127.0.0.1)` first, runs `accept()` on a worker, has the client connect to `getLocalPort()`, sends three UTF-8 lines, and calls `shutdownOutput()`. The server sends back `ECHO:...` for each line and exits when it sees EOF. The client reads until EOF, verifies all echoed lines, and prints deterministic output.

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TcpEchoLinesDemo {
    private static int serveOne(ServerSocket listener) throws IOException {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5_000);
            BufferedReader input = new BufferedReader(new InputStreamReader(
                    peer.getInputStream(), StandardCharsets.UTF_8));
            BufferedWriter output = new BufferedWriter(new OutputStreamWriter(
                    peer.getOutputStream(), StandardCharsets.UTF_8));
            int count = 0;
            String line;
            while ((line = input.readLine()) != null) {
                output.write("ECHO:" + line);
                output.newLine();
                output.flush();
                count++;
            }
            return count;
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 16, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(5_000);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<Integer> serverCount =
                        executor.submit(() -> serveOne(listener));
                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            "127.0.0.1", listener.getLocalPort()), 3_000);
                    client.setSoTimeout(5_000);

                    BufferedWriter output = new BufferedWriter(
                            new OutputStreamWriter(client.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedReader input = new BufferedReader(
                            new InputStreamReader(client.getInputStream(),
                                    StandardCharsets.UTF_8));

                    List<String> messages = List.of(
                            "xin chào", "TCP Java 17", "line=3");
                    for (String message : messages) {
                        output.write(message);
                        output.newLine();
                    }
                    output.flush();
                    client.shutdownOutput(); // FIN: no more client bytes.

                    List<String> actual = new ArrayList<>();
                    String response;
                    while ((response = input.readLine()) != null) {
                        actual.add(response);
                    }
                    List<String> expected = messages.stream()
                            .map(message -> "ECHO:" + message).toList();
                    if (!actual.equals(expected)) {
                        throw new AssertionError(
                                "echo mismatch: " + actual);
                    }

                    System.out.println("bound to loopback: "
                            + listener.getInetAddress().isLoopbackAddress());
                    System.out.println("OS assigned port: "
                            + (listener.getLocalPort() > 0));
                    for (int i = 0; i < actual.size(); i++) {
                        System.out.println("echo " + (i + 1) + ": "
                                + actual.get(i));
                    }
                }
                System.out.println("server line count: "
                        + serverCount.get(5, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac TcpEchoLinesDemo.java
java TcpEchoLinesDemo
~~~

Verified output:

~~~text
bound to loopback: true
OS assigned port: true
echo 1: ECHO:xin chào
echo 2: ECHO:TCP Java 17
echo 3: ECHO:line=3
server line count: 3
~~~

**Do not print the specific port number in expected output**, because the OS may assign a different port on each run. `OS assigned port: true` confirms the actual bound port is positive. The program verifies via `List.equals` that all three echoes match **the exact** expected order and content, not merely checking that three lines arrived.

## 10. Step-by-step breakdown of the text echo program

1. **Listener is ready:** `new ServerSocket(0,16,InetAddress.getByName("127.0.0.1"))` binds before the client thread connects. `getLocalPort()` is used directly without setting a fixed port.
2. **Server worker:** `executor.submit(() -> serveOne(listener))` runs `accept()` on another thread. `Future<Integer>` stores the number of lines the server processed; we avoid printing directly from the server thread to prevent output races.
3. **Connect:** the client calls `connect(new InetSocketAddress("127.0.0.1", listener.getLocalPort()),3000)`. On the server side, `accept()` returns the corresponding `peer`.
4. **Send:** the client writes three lines with `BufferedWriter`, each followed by `newLine()`, then calls `flush()`. `flush` is called **before `shutdownOutput()`** so no bytes are left behind in Java's buffer.
5. **Half-close:** `client.shutdownOutput()` tells the server **there will be no more bytes from the client**, while **the server → client direction can still transmit data**. This is crucial so the socket is not closed outright while the client still needs the echo.
6. **Server side:** `while ((line = input.readLine()) != null)` reads line by line; for each line, it writes `"ECHO:" + line`, a newline, and flushes. When the client half-closes, `readLine` returns `null` after consuming the remaining bytes.
7. **Server closes peer:** exiting `try (Socket peer = listener.accept())` closes the connection socket. The client receives all echoes and then sees EOF when `input.readLine()` returns `null`.
8. **Verification:** the client compares `actual` against `messages.stream().map(...).toList()`. If the echo is wrong, it throws `AssertionError` and the demo fails instead of printing a false success.
9. **Worker result:** `serverCount.get(5, TimeUnit.SECONDS)` retrieves the processed line count, expected to be 3. Finally `executor.shutdownNow()` and `listener.close()` release resources.

Output is printed on the main thread after all echoes have been received, so it **does not depend on whether the server thread runs faster or slower**. A machine at a different speed may get a different port, but the verification lines remain accurate as long as loopback works and no timeout occurs.

## 11. Why use shutdownOutput instead of closing immediately?

`Socket.shutdownOutput()` and `Socket.close()` are very different:

| Call | client → server direction | server → client direction | When to use? |
| --- | --- | --- | --- |
| `client.shutdownOutput()` | Signals end of send direction; peer can see EOF after data | **Remains open** for the client to read the echo | Client finished sending but needs to wait for the response |
| `client.close()` | Closes the socket and its streams | Cannot be used further to receive the echo | Exchange is complete or on error cleanup |
| `serverPeer.close()` | Closes the accepted connection on the server | Client typically receives EOF after any remaining sent bytes | Server has finished processing |
| `client.shutdownInput()` | Affects **the client's receive direction**, not a signal that sending has ended | Client should not continue reading the echo | **Not needed** in this lab's protocol |

Deadlock-avoidance diagram:

~~~text
If the client sends "hello\n" and waits for the server to close the connection:
  client: waits for EOF to know all echoes have arrived
  server: waits for EOF to know the client finished sending the request
  => both can end up waiting on each other.

This lab's solution:
  client: flush -> shutdownOutput() -> read echo until EOF
  server: read until EOF -> close peer
  => both have an explicit termination signal.
~~~

Do not misunderstand `shutdownOutput()` as "tearing down the TCP connection." TCP can **half-close** one direction while the other direction remains active. If `try-with-resources` closes the client immediately after sending without reading, the response can be lost and the test fails to prove a successful echo.

`shutdownOutput` is a good fit for **a protocol that sends the entire request and then reads the response**. For long-lived request/response protocols with multiple round-trips on the same connection, use a **length prefix/delimiter** to mark where each message ends instead of requiring a half-close after every request.

## 12. TCP does not preserve write boundaries: do not read once and treat it as a message

TCP guarantees the order of bytes successfully transmitted over a connection, but **it does not preserve application `write` call boundaries**. For example, if the client calls:

~~~java
output.write(new byte[] {1, 2});
output.write(new byte[] {3, 4, 5});
~~~

*Illustrative snippet: `output` is an `OutputStream` of a connected socket.*

The server might receive those bytes via `read(buffer)` in chunks `[1]`, `[2,3,4]`, `[5]`, or other groupings, depending on the OS and when data arrives. **There is no guarantee** that two `write` calls produce two corresponding `read` calls.

If `read(byte[])` returns `n`, only elements `buffer[0]` through `buffer[n-1]` are newly read data. The rest of the buffer does not belong to this read. You must write back **exactly `n` bytes**:

~~~java
byte[] buffer = new byte[4096];
int n;
while ((n = input.read(buffer)) != -1) {
    output.write(buffer, 0, n);
}
output.flush();
~~~

*Illustrative snippet where `input`/`output` are socket streams. Waiting for EOF fits the example's protocol, not every network protocol.*

- `n > 0`: process exactly `n` bytes; do not read stale contents of the buffer.
- `n == -1`: the peer has ended the send stream in that direction and all data has been consumed; it does not imply every business command succeeded.
- If the socket is reset or broken, `read` may throw `SocketException`/`IOException` instead of returning `-1`.
- `read()` can block if no data or EOF is available yet; `setSoTimeout` limits how long a single read waits.
- With a non-empty buffer, one `read(byte[])` call **does not mean the buffer will be filled**; you must loop until the framing boundary or EOF.

This is why the binary echo server in the next section uses `output.write(buffer,0,n)`, not `output.write(buffer)`.

## 13. Java 17+ program #2: echoing seven binary bytes

Create the file **`TcpEchoBytesDemo.java`**. The program demonstrates **the second way to bind**: `new ServerSocket()` followed by `listener.bind(new InetSocketAddress("127.0.0.1",0),16)`. The server reads with a **3-byte** buffer and echoes exactly `n` bytes each time. The client sends an array containing the NUL byte `0x00`, newline `0x0A`, and `0xFF`, then half-closes its send direction and collects the echoed data.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TcpEchoBytesDemo {
    private static int serveOne(ServerSocket listener) throws Exception {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5_000);
            InputStream input = peer.getInputStream();
            OutputStream output = peer.getOutputStream();
            byte[] buffer = new byte[3];
            int total = 0;
            int n;
            while ((n = input.read(buffer)) != -1) {
                output.write(buffer, 0, n);
                total += n;
            }
            output.flush();
            return total;
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0), 16);
            listener.setSoTimeout(5_000);
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<Integer> serverCount =
                        executor.submit(() -> serveOne(listener));
                byte[] payload = new byte[] {
                        0, 1, 2, 3, (byte) 0xff, 10, 0 };
                byte[] echoed;
                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            "127.0.0.1", listener.getLocalPort()), 3_000);
                    client.setSoTimeout(5_000);
                    client.getOutputStream().write(payload);
                    client.getOutputStream().flush();
                    client.shutdownOutput();

                    ByteArrayOutputStream received = new ByteArrayOutputStream();
                    byte[] chunk = new byte[4];
                    int n;
                    while ((n = client.getInputStream().read(chunk)) != -1) {
                        received.write(chunk, 0, n);
                    }
                    echoed = received.toByteArray();
                }
                System.out.println("OS assigned port: "
                        + (listener.getLocalPort() > 0));
                System.out.println("echoed bytes match: "
                        + Arrays.equals(payload, echoed));
                System.out.println("echoed signed bytes: "
                        + Arrays.toString(echoed));
                System.out.println("server byte count: "
                        + serverCount.get(5, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Run:

~~~bash
javac TcpEchoBytesDemo.java
java TcpEchoBytesDemo
~~~

Verified stdout:

~~~text
OS assigned port: true
echoed bytes match: true
echoed signed bytes: [0, 1, 2, 3, -1, 10, 0]
server byte count: 7
~~~

**Why does `0xFF` print as `-1`?** Java's `byte` type is signed (from `-128` to `127`), so `(byte) 0xff` in `Arrays.toString(byte[])` displays as **-1**. This is **not** `InputStream.read() == -1`. At the `InputStream.read(byte[])` API level, **the return value `-1` of the method itself** indicates EOF, whereas a `0xFF` byte inside **the data array** is completely valid. `Arrays.equals(payload, echoed) == true` verifies that every byte was echoed accurately.

Even though the server uses a 3-byte buffer, you must not claim that every actual `read` **always receives exactly three bytes**. A small buffer caps **the maximum bytes per read**; the exact byte count depends on when the TCP stream delivers data. Only the total `server byte count: 7` is a stable signal in the test.

## 14. Two ways to bind port 0 — a clear comparison

| Approach | State upon creation | Bind operation | Common points |
| --- | --- | --- | --- |
| `new ServerSocket(0,16,InetAddress.getByName("127.0.0.1"))` | **Already bound** when constructor completes | Inside the constructor | OS picks port, IPv4 loopback |
| `new ServerSocket()` | **Unbound** | `bind(new InetSocketAddress("127.0.0.1",0),16)` | OS picks port, IPv4 loopback |

**Both** require `accept()` to obtain the client's socket. **Both** use `getLocalPort()` after binding. **Do not** create a client `Socket` connecting to port 0. **Do not** send data directly through `ServerSocket`.

If a server needs to determine IP/backlog configuration later, the second approach lets you create the object first and bind afterward. In simple tests, the first approach is more concise. Binding an unavailable address or an already-occupied port (with a fixed port) can throw `BindException`/`IOException`; with port 0, the OS reduces collision risk, but that does not mean all networking issues disappear.

## 15. Framing for real-world TCP: common strategies

| Strategy | Message boundary | Pros | Limitations |
| --- | --- | --- | --- |
| **Newline-delimited text** | `\n` or valid newline | Very easy to debug, great for text echo | Payloads with newlines need escaping; length limits |
| **Length-prefix** | e.g., 4-byte length + N payload bytes | Supports binary and multiple consecutive messages | Must validate length, byte order, max N |
| **Fixed-size frame** | Each record is N bytes | Simple if schema is fixed | Hard to extend; must read all N bytes |
| **Arbitrary delimiter** | Designated separator char/byte | Easy to read in simple protocols | Must escape/encode delimiter in payload |
| **EOF-delimited single message** | One side calls `shutdownOutput()`/closes send | Easy for **a single payload** | Cannot support multiple requests/responses on a persistent connection without adding framing |
| **Standard protocol** | HTTP, WebSocket, etc. | Framing/semantics already defined | Must follow protocol spec; do not mix raw TCP ad hoc |

Length-prefix conceptual example:

~~~text
Message 1:
  00 00 00 05 | 48 65 6C 6C 6F
      len=5    |     "Hello"

Message 2:
  00 00 00 03 | 01 02 03
      len=3    |   3 binary bytes
~~~

In Java, `DataOutputStream.writeInt(length)` writes 4 big-endian bytes; `DataInputStream.readInt()` can read the length header according to the corresponding protocol. After validating `0 <= length <= MAX_FRAME_SIZE`, use `readFully(byte[])` or a loop to read all bytes; if EOF arrives before the expected byte count, handle `EOFException` as a **truncated message**, not as a complete message.

**Framing security:** Never allocate `new byte[length]` when `length` is peer-controlled without checking bounds first, and never trust that every client will send all bytes. With UTF-8, byte length differs from the number of Java chars/codepoints; set limits in **bytes** appropriate to server resources.

## 16. Timeouts and exceptions: connect, accept, and read are not the same thing

| Operation | How it is bounded in the demos | On timeout/error |
| --- | --- | --- |
| Server waiting for a client | `ServerSocket.setSoTimeout(5_000)` before `accept()` | `SocketTimeoutException` if waiting for accept exceeds limit |
| Client establishing TCP connection | `Socket.connect(addr,3_000)` | `SocketTimeoutException` or `ConnectException`/I/O error depending on case |
| Reading data on a `Socket` | `Socket.setSoTimeout(5_000)` | `SocketTimeoutException` when **a single read** waits too long |
| Waiting for server worker to finish | `Future.get(5, TimeUnit.SECONDS)` | `TimeoutException` on the waiting thread; does not automatically close the socket |
| Writing data | `OutputStream.write` | May block or throw `IOException`; `SO_TIMEOUT` is not a total write deadline |
| Closing/half-closing | `shutdownOutput`, `close` | May throw `IOException` on invalid state or I/O error |

**Do not confuse EOF with a timeout:** `BufferedReader.readLine()==null` or `InputStream.read(...) == -1` under normal circumstances indicates the peer has ended **the send direction**. `SocketTimeoutException` means waiting too long during a read/accept without enough events to proceed. `Connection reset` is typically an abnormal TCP error, not the end marker of a properly sent message.

Do not treat `EOF` after receiving **part** of a length-prefix frame as success: that is **truncated** data. This echo example knows in advance there are three lines and seven bytes, so it verifies the entire content; real applications need lengths, checksums, or protocol responses to know they received everything.

`setSoTimeout` is not a total deadline for an entire long-running call and does not stop a slow peer from trickling one byte just before each timeout. Production systems need total deadlines, byte/line limits, quotas, and socket cancellation/closing policies.

## 17. Resources and connection closing order

Both programs use `try (ServerSocket listener = ...)` for the listening socket and `try (Socket peer = listener.accept())` / `try (Socket client = new Socket())` for accepted or actively initiated connections. Closing a `Socket` closes its associated input/output streams. This avoids "port still in use because the process hasn't closed the socket."

Order in the test:

~~~text
1. Bind ServerSocket(127.0.0.1, 0)
2. Start worker waiting on accept()
3. Client connects to the actual port
4. Client sends and flushes data
5. Client calls shutdownOutput()
6. Server reads until EOF, echoes, closes accepted Socket
7. Client reads echo until EOF and verifies
8. Client closes, server worker completes
9. Shut down executor and close ServerSocket
~~~

`serverCount.get(...)` is called after the client has finished reading the response and closed, so the server task has already had a chance to finish. `executor.shutdownNow()` in `finally` cleans up the worker; if a worker is stuck on I/O, an interrupt may **not be enough** to unblock all classic socket calls, which is why timeouts and closing the socket/listener are combined. The demos set bounded timeouts for accept/read to avoid hanging indefinitely under normal conditions.

**`ServerSocket.close()` differs from `Socket.close()`:** closing the listener stops accepting new connections; accepted sockets have their own lifecycles. In a multi-client server, you must track and close accepted sockets individually rather than assuming closing only the listening socket cleans up all clients.

## 18. If you want to echo multiple clients concurrently

Both demos intentionally accept **one** connection to keep testing simple. To run a long-lived TCP echo service, the typical model is:

~~~text
Bound ServerSocket listener
        |
while (running):
    Socket peer = listener.accept()
        |
        +--> bounded executor handles peer and closes peer after session
        |
shutdown:
    stop accepting -> close listener -> wait for workers with deadline -> cleanup
~~~

Production designs must cap active connections, thread counts, queue sizes, bytes per client, wait times, and enforce auth/TLS as needed. Do not spawn an unbounded platform thread per client if an attacker can open huge numbers of connections.

Reasonable changes when scaling out:

- Keep a shared `ServerSocket` and give each accepted `Socket` an independent handler; never mix streams from two clients.
- Use a bounded `ExecutorService` with rejection/quota policies and graceful shutdown.
- Avoid sharing a single client's `BufferedReader`, `BufferedWriter`, or `Socket` across multiple unsynchronized writers.
- For multiple messages on a long-lived connection, use explicit framing instead of expecting EOF after each request.
- If you need backpressure or high scale, consider Java NIO `SocketChannel`/`Selector`, though that is an extension and **not required** to complete basic TCP echo.

## 19. Why don't the demos "expose to the external network"?

The demos bind `127.0.0.1`, so connections only come from the corresponding local network namespace and are not exposed directly on the LAN under standard configurations. However, **loopback does not replace authentication** when untrusted processes share the same machine or when environments use port forwarding, proxies, or container networking.

`Socket` and `ServerSocket` in these examples transmit **plaintext TCP**, **without TLS**. Do not send sensitive information or real credentials. When encryption/authentication is needed in real systems, use `SSLSocket`/`SSLServerSocket` or an appropriate secure protocol; verify certificates and hostnames, and never use "trust-all".

Beyond binding loopback, avoid logging sensitive personal content in demos and do not assume firewalls, containers, or CI runners allow every loopback connection. If an environment restricts socket binding, tests may be rejected even when the source code is correct.

## 20. Most common mistakes

| Misconception or buggy code | Consequence | Fix |
| --- | --- | --- |
| Server binds `port=0`, then client connects to `port=0` | Client uses the wrong endpoint | Read `ServerSocket.getLocalPort()` |
| Hard-coding `8080` even though OS assigned another port | `Connection refused` | Use the exact bound port |
| Opening a socket to pick a port and closing it before server binds | Race where another process grabs the port | Keep the very listener bound to port 0 |
| Binding IPv6 loopback while connecting to IPv4 loopback | Address family mismatch | Use `127.0.0.1` on both sides |
| Binding `0.0.0.0` when only local access is needed | May expose service to external interfaces | Bind loopback explicitly |
| Calling `accept()` before `connect()` on the same thread | Thread blocks forever | Use a separate worker for the server |
| Not calling `flush()` after `BufferedWriter.write` | Server waits for newline/data still in buffer | Flush at the right time |
| Sending text without defining a delimiter or length | `readLine()` or parser waits forever | Define explicit framing |
| Treating `readLine() == ""` as EOF | Confuses valid empty lines | EOF is `null` |
| Calling `read(buffer)` once and assuming the whole message arrived | Data may arrive across multiple chunks | Loop until frame boundary |
| Calling `output.write(buffer)` ignoring actual `n` read | Sends stale/extra bytes from buffer | `write(buffer,0,n)` |
| Comparing a `0xFF` byte with `read`'s `-1` return | Confuses data with EOF | Distinguish signed byte from byte count returned |
| Client calls `close()` before receiving the echo | Loses the response read direction | `shutdownOutput` then read until EOF |
| Both client and server wait for EOF without half-close | Can deadlock | Design explicit termination signals |
| Believing `setSoTimeout` caps the entire session | Slow peer can stretch across many reads | Add total deadline and size limits |
| Not using try-with-resources | Leaks sockets, ports, or threads | Close listener, peers, and executor |
| Using `readAllBytes()` on an unbounded stream | Can exhaust RAM or wait forever for EOF | Use bounded reading and framing |
| Assuming TCP provides business-level "exactly-once delivery" | TCP only moves a byte stream | Implement ACK/idempotency at the application layer |
| Passing `getBytes()` with the default charset | May corrupt Vietnamese text on other machines | `StandardCharsets.UTF_8` |
| Thinking backlog is the number of concurrent clients handled | Misunderstands the accept queue | Separate backlog from worker concurrency |

## 21. Testing the program layer by layer

A good test should verify each layer, not just "no exception thrown":

1. **Proper bind:** `listener.getInetAddress().isLoopbackAddress()==true` and `getLocalPort()>0`. No need to know the port number.
2. **Proper connect:** client calls `connect` to the right IPv4/port. With the wrong port, you typically see `ConnectException`.
3. **Framing:** line demo receives exactly **three** lines and each echo starts with `ECHO:`, with accurate UTF-8 Vietnamese diacritics.
4. **EOF/half-close:** client calls `shutdownOutput()`, server exits `readLine` at EOF, client receives echoes and then sees EOF when the server closes.
5. **Byte integrity:** binary demo uses `Arrays.equals` to compare all 7 bytes, including NUL and `0xFF`.
6. **Read counts:** server writes only `n` bytes per read, total count equals 7; do not assume each `read` receives the full buffer size.
7. **Cleanup:** server worker finishes, socket/listener close. Re-running the program multiple times produces no fixed-port conflicts.
8. **Timeout:** a client/peer that sends no data should exhibit clear timeout behavior; do not let tests hang forever.
9. **Negative tests:** try connecting to a wrong port, an unresponsive server, framing/truncated frame errors, and classify exceptions properly.

Because both programs print booleans instead of random port numbers, stdout can be checked deterministically. As long as loopback is permitted and an overloaded machine does not trigger timeouts, output order and line count do not depend on worker scheduling.

## 22. Knowledge check questions

**Question 1.** Does `new ServerSocket(0,16,InetAddress.getByName("127.0.0.1"))` create a server listening on port 0?

*Answer:* Not in the way clients use it. Port 0 **asks the OS to assign a real port**, and that port is read via `getLocalPort()` after binding.

**Question 2.** What does `ServerSocket.accept()` return, and is `ServerSocket` used to read client data?

*Answer:* `accept()` returns a **new `Socket`** representing an accepted connection. Read/write using that Socket's input/output streams, not `ServerSocket`.

**Question 3.** Why must `accept()` and `connect()` run on different threads in the demos?

*Answer:* `accept()` blocks waiting for a client; if called before `connect()` on the same thread, `connect` is never initiated.

**Question 4.** Is it a TCP bug if the client makes three `write` calls but the server sees two `read` calls?

*Answer:* No. TCP is a byte stream; `write` boundaries do not match `read` boundaries. You must frame messages yourself and handle the exact `n` bytes.

**Question 5.** Is `BufferedReader.readLine()` returning an empty string EOF?

*Answer:* No. An empty line is `""`. EOF is `null`.

**Question 6.** Why does the client use `shutdownOutput()` instead of `close()` immediately after sending?

*Answer:* `shutdownOutput()` signals no more bytes will be sent while still allowing the echo to be received; `close()` closes the entire socket so reading can no longer continue.

**Question 7.** `Arrays.toString(new byte[]{(byte)0xff})` prints `[-1]`. Is that TCP EOF?

*Answer:* No. Java's `byte` type is signed. EOF is only **the int return value of `InputStream.read`**, not a data byte with value `0xFF`.

**Question 8.** Does `Socket.setSoTimeout(5000)` guarantee an entire TCP session finishes within 5 seconds?

*Answer:* No. It limits the wait time of **each individual read where it applies**; separate session deadlines and data limits are needed.

**Question 9.** Why does `127.0.0.1` differ from `0.0.0.0` when binding?

*Answer:* `127.0.0.1` is loopback serving only local traffic; `0.0.0.0` listens on all IPv4 interfaces and can expose the service to external networks.

## 23. Hands-on exercises

1. Run `TcpEchoLinesDemo` on Java 17+, replace the three test lines with new Vietnamese text, verify `List.equals` still PASSES and echoes preserve Unicode accurately.
2. Print the actual value of `listener.getLocalPort()` in a separate run and run it a few times to observe OS port selection; **do not hard-code** that number into main test output.
3. Convert demo 1 to `new ServerSocket()` followed by `bind(new InetSocketAddress("127.0.0.1",0),16)`; explain the two phases: create and bind.
4. Remove `output.flush()` (in a test copy) and explain why the server can wait on buffered bytes and time out; restore flush.
5. Remove `client.shutdownOutput()` and predict what client/server will wait for; observe the socket timeout in a time-bounded test, then restore half-close.
6. In the line demo, send an empty line `""`; verify it is echoed as `ECHO:` and **not** mistaken for EOF.
7. In the binary demo, change the server buffer from 3 to 1 and 8, confirming `Arrays.equals` always succeeds even though the number of `read` calls changes.
8. Add a payload containing `0x00`, `0xFF`, and invalid UTF-8 bytes as raw data; verify byte-for-byte echo without decoding as text.
9. Intentionally change the server to `output.write(buffer)` instead of `write(buffer,0,n)` and observe extra/stale bytes appearing in the final chunk; restore the correct version.
10. Design a 4-byte big-endian length-prefix frame + payload (max limit 4096 bytes), use `DataInputStream.readFully` to read each full message, and return an error when EOF occurs before the declared length.
11. Extend the server into an `accept` loop with a bounded executor and a max client limit, ensuring the accepted socket is closed in every handler.
12. Try connecting to a port with no listener and classify `ConnectException`, without confusing it with `SocketTimeoutException` or EOF.
13. Run in a container/CI environment, identifying the loopback namespace and the requirement for client/test to reside in the same namespace.
14. Write a cleanup checklist for graceful shutdown: stop accepting, close listener, drain/close accepted sockets, and shut down the executor with a deadline.
15. Discuss what changes if an echo server handles real sensitive data: TLS, message length limits, auth, not logging sensitive data, and protection against denial-of-service.

## Official API documentation

- [`ServerSocket` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): constructors, `bind`, port 0, `getLocalPort`, `accept`, `setSoTimeout`, `close`.
- [`Socket` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `connect`, `setSoTimeout`, input/output streams, `shutdownOutput`, half-close, `close`.
- [`InputStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `read(byte[])`, actual bytes read, and `-1` at EOF.
- [`BufferedReader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): `readLine()`, `null` at end of lines.
- [`BufferedWriter` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html): `newLine`, `flush`, and buffering.
- [`DataInputStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt`, `readFully` for length-based framing.
- [`StandardCharsets` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): `UTF_8` charset for consistent text exchange.
