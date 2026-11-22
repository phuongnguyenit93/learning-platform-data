# ServerSocket: Binding an Address, Listening, and Accepting Connections

## 1. Overview: How Does a TCP Server Open a Port?

In Java, `java.net.ServerSocket` is the object that **listens for incoming TCP connections**. It represents the server's **listening socket**: selecting a **local IP address** and **port**, asking the operating system to allow receiving connections at that endpoint, and then waiting to receive a connection with `accept()`. Each time `accept()` succeeds, Java returns **a new `java.net.Socket`** representing a TCP connection with a specific client.

The three core operations of this topic:

1. **Bind an address:** specify the **local IP + TCP port** pair that the server will use; for example `127.0.0.1:8080` to serve only on loopback.
2. **Listen:** after binding succeeds, the listening socket is placed in a state ready to receive connection requests. The traditional `ServerSocket` API **does not have a separate public `listen()` method**: the bind/constructor operation already sets up listening capability at the operating system level.
3. **Accept:** `server.accept()` waits for a ready connection, then returns a **connected `Socket`**; use `getInputStream()` and `getOutputStream()` on the received socket to exchange bytes.

~~~text
Java Server                                OS / TCP                            Client
new ServerSocket()                         Not yet bound to an endpoint
setReuseAddress(...)                       Set options before bind
bind(local-IP, port, backlog) -------->    BIND + LISTEN
accept() ------------------------------>   Wait for connection in queue
                                           SYN / SYN-ACK / ACK  <-------- connect(...)
accept() <------------------------------   Connection available to dequeue
returns Socket clientSocket                TCP connection ESTABLISHED
clientSocket.getInputStream() <---------   TCP byte stream  <-------------- write(...)
clientSocket.getOutputStream() -------->   TCP byte stream  -------------> read(...)
close(clientSocket)                        Close accepted connection
accept()                                   Continue accepting other clients
close(serverSocket)                        Stop accepting new connections
~~~

The diagram is a logical description and does not fix an absolute ordering between `connect()`, the TCP handshake, and when the application calls `accept()`. On many systems, **the TCP handshake can complete and the client `connect()` can return before the server's Java thread calls `accept()`**; the operating system temporarily holds the connection in a queue. **`accept()` is not where Java itself performs the entire handshake in application code**.

## 2. Distinguishing a Listening `ServerSocket` from a Connected `Socket`

| Property | `ServerSocket` | `Socket` returned by `accept()` |
|---|---|---|
| Role | Listens for new connections at a local endpoint | Exchanges data with **one** TCP peer |
| Primary address/port | Local bind address and listening port | Local address/port **and** remote address/port of the connection |
| Primary API | `bind(...)`, `accept()`, `setSoTimeout(...)`, `close()` | `getInputStream()`, `getOutputStream()`, `setSoTimeout(...)`, `close()` |
| When no new client has arrived | Blocking `accept()` can wait | Unrelated to accepting new connections |
| When receiving bytes | Does not read application data | Reads via the input stream |
| When closed | Stops accepting new clients | Terminates that specific client's connection |

A server can have **one `ServerSocket` on port 8080** while simultaneously managing many accepted `Socket` instances. Each connection has a distinct **TCP 4-tuple**: local IP, local port, remote IP, remote port. Therefore, accepted sockets can share local port 8080 and still be independent connections.

**Do not call `getInputStream()` on `ServerSocket`**: it only listens. **Do not use `ServerSocket.accept()` to read an HTTP/chat request**: `accept()` returns the connection; application data is read afterward on the accepted socket.

## 3. Creating and Binding an Address Properly

### 3.1. Common Constructors and `bind`

~~~java
// Illustrative snippet: each option is a separate way to create a server.
ServerSocket a = new ServerSocket();             // Not yet bound
ServerSocket b = new ServerSocket(8080);         // Bind and listen immediately
ServerSocket c = new ServerSocket(8080, 128);    // Bind with requested backlog
ServerSocket d = new ServerSocket(
        8080, 128, InetAddress.getLoopbackAddress());
~~~

These lines are **alternative examples**, not meant to run multiple listeners simultaneously on the same port 8080. Constructors that take a port argument **bind immediately** and may throw `IOException` if binding fails. With `ServerSocket()`, you set options first and then call:

~~~java
// Snippet, placed inside a method that handles IOException:
try (ServerSocket server = new ServerSocket()) {
    server.setReuseAddress(true);  // Should be set before bind if used
    server.bind(
        new InetSocketAddress(InetAddress.getLoopbackAddress(), 8080),
        128
    );
    // After bind succeeds, the server is ready for accept().
}
~~~

`bind(SocketAddress endpoint, int backlog)` takes:

- **`endpoint`:** usually an `InetSocketAddress`, consisting of the **server machine's own local** address and TCP port, not the address of the client about to connect.
- **`backlog`:** the length of the **queue of connections waiting to be accepted** requested by the program; its actual meaning and limit depend on the operating system/implementation.
- If you only use `bind(endpoint)`, the JDK uses an implementation-dependent default backlog. For the simple constructors, the Java 17 documentation describes the default requested value as **50**; the actual number may be adjusted by the operating system.
- **`port = 0`:** the operating system picks a free port, usually from the ephemeral range; retrieve the actual port with `server.getLocalPort()`. This is a good choice for unit/integration tests to avoid hard-coding a port that might be in use.
- **`bind(null)`:** asks the JVM/system to pick a local endpoint and an ephemeral port; for a server that must have a fixed port for real clients, provide an explicit endpoint.
- Valid ports are **0–65535**, but port 0 is a request for automatic port assignment rather than meaning the server will keep listening on TCP port 0.

### 3.2. Bind One IP or All IPs?

A machine can have loopback, LAN addresses, VPN interfaces, or multiple IPv4/IPv6 addresses.

| Bind address | Meaning | When to use |
|---|---|---|
| `127.0.0.1` | IPv4 loopback, only matching local connections over loopback | Demos, host-internal administration tools |
| `::1` | IPv6 loopback | Environments that want IPv6 loopback only |
| `0.0.0.0` | IPv4 wildcard, matching local IPv4 addresses | Servers that need to accept from multiple IPv4 interfaces |
| `::` | IPv6 wildcard; whether IPv4 is also accepted depends on dual-stack configuration | IPv6 servers |
| A LAN IP of the machine | Only that interface/address | Services listening on a specific network |

Explicit examples:

~~~java
// IPv4 loopback only
server.bind(new InetSocketAddress("127.0.0.1", 8080), 128);

// Port 8080 on any local IPv4 address
server.bind(new InetSocketAddress("0.0.0.0", 8080), 128);
~~~

These two lines **do not run consecutively on the same `ServerSocket`**: it can only be bound **once**. After a successful bind, calling `bind` again will fail. In the complete example later, `InetAddress.getLoopbackAddress()` is used so it does not depend on whether the machine supports IPv4 or IPv6 loopback.

**Choose the bind address based on the desired reachability scope.** Wildcard binding makes the service reachable from multiple interfaces, though it can still be blocked externally by firewalls, NAT, container networks, or operating system policies. Loopback binding prevents other machines from connecting directly to that port over the LAN, even if the firewall is open.

### 3.3. DNS and Hostnames Are Not "Addresses to Bind"

`new InetSocketAddress("localhost", 8080)` requires hostname resolution; `localhost` may resolve to `127.0.0.1` or `::1` depending on the environment. If the server binds only IPv4 while the client uses IPv6, or vice versa, the connection attempt may fail. For demos, choose the same `InetAddress` object for both server and client to avoid a mismatch.

**Do not bind to the public IP of a remote machine**: a server can only bind addresses valid for its local network stack. When a machine is behind NAT or running in a container, the public address seen by clients often differs from the actual address/interface on the machine/container.

## 4. How "Listen" Actually Works and What `backlog` Means

In C/BSD sockets, the sequence `socket → bind → listen → accept` is often referenced. Java `ServerSocket` provides an abstraction: the constructor binds or you call `bind` yourself, after which the socket is ready to listen; **there is no `server.listen()` in the Java API**.

When a client calls `connect(remote)`:

1. The operating systems on both sides handle the TCP handshake mechanism, such as SYN → SYN-ACK → ACK in the common case.
2. Eligible connections are placed into a queue for the server to accept, depending on the TCP implementation and network state.
3. A Java thread calling `accept()` retrieves a ready connection from the operating system and is returned **a new `Socket`**.
4. The listening `ServerSocket` remains alive to accept subsequent connections.

`backlog` is a **hint/request** for the number of connections waiting to be accepted; the Java 17 Javadoc notes its semantics are *implementation-specific*: the operating system may cap or ignore the parameter. Do not define backlog as "the number of threads allowed to run," "total currently connected clients," or "maximum HTTP requests."

- **Small backlog + overly slow `accept()` handling:** many concurrent clients may be refused, time out, or establish slowly, depending on the OS/network.
- **Large backlog** does not fix an exhausted worker pool, sockets held open too long, or CPU saturation; the queue only smooths out bursts at the acceptance stage.
- **`new ServerSocket(8080, 0)`** should not be used to assert "no queue": a non-positive backlog uses an implementation-dependent default.
- Do not write tests assuming `backlog=1` guarantees only one connection is allowed. The outcome depends on the OS, handshake, kernel queues, `accept` speed, and how options are applied.

## 5. `accept()`: Waiting, Returning, and Looping to Accept Clients

`Socket accepted = server.accept();` is a **blocking call** in standard `ServerSocket`: when no connection is ready, the thread waits. When one is available, the method returns a new `Socket` connected to a peer, or throws an exception on timeout/close/error.

~~~java
// Illustrative snippet; server is already bound:
while (!server.isClosed()) {
    try {
        Socket accepted = server.accept();
        // Hand off Socket to a worker, or handle it within resource management scope.
    } catch (SocketTimeoutException timeout) {
        // No client arrived within the wait time; the server can still continue accepting.
    }
}
~~~

This is a **conceptual skeleton, not a complete program**: production code needs to handle `IOException` when closing the server, bound worker resources, and ensure **every accepted `Socket` is closed**. If accepting and handling a client happens entirely on the same thread, other clients must wait until handling finishes; depending on the application, delegate to a thread pool or a non-blocking model.

### 5.1. Setting a Timeout for `accept()`

~~~java
server.setSoTimeout(2_000); // accept() waits at most ~2 seconds
try {
    Socket client = server.accept();
    // Manage/close client after handling.
} catch (SocketTimeoutException e) {
    // accept wait timed out; the listening socket can still be used.
}
~~~

`setSoTimeout(int milliseconds)` on **`ServerSocket`** applies to **`accept()`**, not to reading data from a client. A value of **0** (the default) means **infinite timeout via SO_TIMEOUT**; negative values are rejected. Set the timeout **before calling `accept`**.

The returned socket has its **own** I/O timeout. If you want to prevent slow-sending clients from hanging a worker, configure it additionally:

~~~java
client.setSoTimeout(3_000); // timeout for client Socket input read operations
~~~

A `SocketTimeoutException` from `accept` indicates that **no connection was accepted within the wait period**, not that the network is broken. A `SocketTimeoutException` when reading input from an accepted `Socket` indicates **waiting too long for data bytes**; those are two different bottlenecks. An `accept` timeout does not automatically close `ServerSocket`, and a read timeout does not automatically close the accepted `Socket`.

### 5.2. `accept()`, Handshake, and Request Are Three Different Things

A single TCP connection can carry multiple requests/messages according to application rules. After `accept()`, you must read the byte stream with explicit **framing** (length, delimiter, HTTP protocol, etc.) if you want to know when a complete message has arrived. `Socket.getInputStream().read()` may read fewer bytes than expected; do not rely on a single `read` to infer an entire request.

For HTTPS, a plain `ServerSocket` only handles **plain TCP**; encryption/TLS handshake requires corresponding classes such as `javax.net.ssl.SSLServerSocket`/`SSLSocket` (or a library/server framework). TCP `accept()` does not mean the TLS handshake or HTTP parsing has completed.

## 6. Complete Java 17+ Example: Loopback Bind, Accept, Data Exchange, Timeout

The following program runs **both server and client in the same JVM** over loopback, requiring no Internet access and occupying no fixed port. It demonstrates:

- Creating an **unbound `ServerSocket`**, setting `SO_REUSEADDR` and an accept timeout, then binding to loopback with **port 0** and backlog 16.
- Retrieving the actual assigned port with `getLocalPort()`.
- A server-side task calling `accept()` and replying to the client on its **own `Socket`**.
- The client connecting, sending the line `PING`, and receiving `ACK:PING`; the server side returns the received content.
- Afterward, with no new client arriving, `accept()` waits 200 ms and throws `SocketTimeoutException`; the listener remains valid.
- All `Socket` instances are closed via `try-with-resources`, and the executor is shut down.

Create the file **`ServerSocketLifecycleDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ServerSocketLifecycleDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (ServerSocket listener = new ServerSocket()) {
            listener.setReuseAddress(true);
            listener.setSoTimeout(3_000);
            listener.bind(new InetSocketAddress(loopback, 0), 16);

            System.out.println("bound=" + listener.isBound());
            System.out.println("loopback=" +
                    listener.getInetAddress().isLoopbackAddress());
            System.out.println("portAssigned=" + (listener.getLocalPort() > 0));

            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> request = executor.submit(() -> {
                    try (Socket peer = listener.accept();
                         BufferedReader input = new BufferedReader(
                             new InputStreamReader(peer.getInputStream(),
                                 StandardCharsets.UTF_8));
                         BufferedWriter output = new BufferedWriter(
                             new OutputStreamWriter(peer.getOutputStream(),
                                 StandardCharsets.UTF_8))) {
                        peer.setSoTimeout(3_000);
                        String line = input.readLine();
                        output.write("ACK:" + line);
                        output.newLine();
                        output.flush();
                        return line;
                    }
                });

                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            loopback, listener.getLocalPort()), 3_000);
                    client.setSoTimeout(3_000);
                    BufferedWriter output = new BufferedWriter(
                        new OutputStreamWriter(client.getOutputStream(),
                            StandardCharsets.UTF_8));
                    BufferedReader input = new BufferedReader(
                        new InputStreamReader(client.getInputStream(),
                            StandardCharsets.UTF_8));

                    output.write("PING");
                    output.newLine();
                    output.flush();
                    System.out.println("reply=" + input.readLine());
                }

                System.out.println("received=" +
                        request.get(5, TimeUnit.SECONDS));
                listener.setSoTimeout(200);
                try {
                    listener.accept();
                    System.out.println("unexpectedSecondClient");
                } catch (SocketTimeoutException expected) {
                    System.out.println("acceptTimeout=true");
                }
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 ServerSocketLifecycleDemo.java
java ServerSocketLifecycleDemo
~~~

**Verified stdout** (compiled targeting Java 17 and run on OpenJDK 24):

~~~text
bound=true
loopback=true
portAssigned=true
reply=ACK:PING
received=PING
acceptTimeout=true
~~~

The demo prints `portAssigned=true` rather than a random port number so stdout can be verified consistently. `Future.get(...)` lets the main thread wait for the server task to finish reading `PING` and sending the reply before attempting `accept()` again. `readLine()` and `newLine()` here create **line-based framing**, avoiding waiting forever due to a missing terminator.

**Note:** the example uses timeouts of a few seconds to avoid hanging indefinitely if the runtime environment restricts loopback or has unusual scheduling. In production systems, design timeout logic according to SLAs rather than copying these test numbers.

## 7. Checking State Before and After Binding

| API | Before bind | After successful bind | After calling `close()` |
|---|---|---|---|
| `server.isBound()` | `false` | `true` | **Still `true` if previously bound** |
| `server.isClosed()` | `false` if newly created | `false` | `true` |
| `server.getLocalPort()` | `-1` | Actual port | May still return the bound port |
| `server.getInetAddress()` | `null` | Bound local IP | May still return the bound address |
| `server.getLocalSocketAddress()` | `null` | Local endpoint | May still return the bound endpoint |

**Do not use `isBound()` alone as a check that the server is still active**: Java explicitly documents that a socket that was bound and then closed still reports having been bound. For server code, manage lifecycle explicitly and check `isClosed()`, errors from `accept()`, and worker state. `getLocalPort() > 0` only confirms a port was assigned in the demo; it does not prove clients from the Internet can reach it.

## 8. Closing the Listener and Active Connections

There are two levels of resources:

1. **`ServerSocket`:** represents the listening endpoint, accepting new connections.
2. **Each accepted `Socket`:** represents a TCP connection exchanging data, with its own input/output streams and timeout.

When closing `ServerSocket`:

- Subsequent `accept()` calls cannot be used on a closed listener.
- A thread blocked in `accept()` may be woken up with a `SocketException` when the listener is closed.
- **Existing accepted `Socket` instances are not automatically all closed** just because the listener closes; the application must own/close each socket, finish in-flight requests, or define its own shutdown strategy.
- Using `try-with-resources` in separate scopes for the listener and accepted sockets helps prevent descriptor leaks.
- If a graceful shutdown is needed: stop accepting new clients, signal workers to finish or cancel by a deadline, close remaining accepted sockets, then wait for the executor to stop.

This is why production TCP servers typically have a lightweight **accept loop** and a separate connection-handling mechanism. To avoid resource exhaustion, do not spawn unbounded threads for every client; bound active connections/workers, work queues, read timeouts, and message lengths.

## 9. Common Errors and How to Verify Them

| Symptom | Possible cause | How to check |
|---|---|---|
| `BindException: Address already in use` | Another socket/process is already using the local IP/port, or OS rules disallow rebinding | Check the exact IP/port, old listeners, container port mappings, and `SO_REUSEADDR` if appropriate |
| `BindException: Cannot assign requested address` | Binding an IP not assigned to the machine/interface | Choose an actual local address, loopback, or appropriate wildcard |
| Client `Connection refused` | No listener accepting at the target endpoint, or connection rejected by network/firewall | Compare bind address, actual port, server state, and network |
| Client cannot connect from LAN but works on the server itself | Server bound `127.0.0.1` / `::1` | Bind a LAN address or wildcard when remote access is actually needed; configure firewall appropriately |
| Client using `localhost` cannot connect | IPv4/IPv6 mismatch | Print actual addresses on both sides, use a literal IP or the same `InetAddress` |
| `accept()` waits forever | No new client, `SO_TIMEOUT` is 0 | Check network/listen port; set `server.setSoTimeout(...)` if needed |
| `accept()` throws `SocketTimeoutException` | Waited past `SO_TIMEOUT` without receiving a connection | Decide whether to retry or shut down; the listener is still usable |
| `accept()` throws `SocketException` after shutdown | Listener was closed while waiting | Handle as an intentional shutdown path if the server is already closed |
| Client connects but sending a request gets no response | Worker not reading/flushing properly, missing framing, worker blocked | Distinguish `accept` from `read`/`write`, check newline/length and the accepted socket's timeout |
| Many clients report timeouts under load | Slow accept loop/workers, backlog/OS queues, resource limits | Measure accept rate, active connections, worker queue, CPU, and timeouts |
| `accept()` on `ServerSocket` from a non-blocking `ServerSocketChannel` | Non-blocking mode API is incompatible with the wrapper's blocking accept | Use `ServerSocketChannel.accept()` in the proper mode and handle `IllegalBlockingModeException` per API |

**Do not confuse `SO_REUSEADDR` with the ability to run two independent listeners on the exact same `IP:port`.** This option has OS-dependent semantics, is usually useful when restarting a server with connections in `TIME_WAIT`, and should be set before bind; it is not a universal license for two arbitrary processes to listen on the same endpoint.

**Checking ports:** on Linux you can use `ss -ltn`; on Windows use `netstat -ano -p tcp` or `Get-NetTCPConnection` (PowerShell). When you see the `LISTEN` state, still verify the exact local address and port; a socket being in `LISTEN` does not guarantee all clients across firewalls/NAT can reach it.

## 10. When to Use `ServerSocket` and When to Choose Another API?

- **Learning TCP mechanics or building a small server:** `ServerSocket` + `Socket` is a simple choice for understanding bind, listen, accept, and byte streams.
- **Servers with many concurrent connections:** `ServerSocket` can still be used, but requires an executor/pool, connection limits, and a closing strategy; do not treat backlog as a capacity metric.
- **Non-blocking/event-loop servers:** consider `java.nio.channels.ServerSocketChannel` + `Selector`; `accept` mechanics can be non-blocking unlike the classic API. Switch models only when there is a clear need.
- **HTTPS/TLS:** use `SSLServerSocket` or a server framework that supports TLS; a raw `ServerSocket` only accepts unencrypted TCP connections.
- **Application HTTP:** usually use an HTTP server/framework that already handles framing, request parsing, keep-alive, TLS, and protocol errors. Writing `ServerSocket` yourself to understand the mechanics is useful, but production HTTP has many responsibilities beyond `accept`.

## 11. Self-Check Questions

**1. With `new ServerSocket(8080)`, do you still need to call `listen()`?** No. The constructor already binds and sets up the listener; Java `ServerSocket` has no public `listen()` method.

**2. Is it valid to do `new ServerSocket()` and immediately call `accept()`?** No. The listener is not bound to an endpoint yet; you must call `bind(...)` first.

**3. Does `accept()` return the data sent by the client or a connection?** It returns a **connected `Socket`**. Read data through that socket's input stream.

**4. Does `backlog=128` mean the server can only have 128 active clients?** No. It is a requested value for the queue waiting to be accepted, with limits/enforcement depending on the OS; the number of accepted clients depends on application design and resources.

**5. Does `port=0` make the server listen on TCP port 0?** No. The operating system assigns an actual port; retrieve it with `getLocalPort()`.

**6. Does `setSoTimeout(1_000)` on `ServerSocket` make `InputStream.read()` on an accepted `Socket` time out?** No. Set the read timeout on the **accepted `Socket`** if needed.

**7. After closing the listener, does `isBound()` become `false`?** Not necessarily; a `ServerSocket` that was once bound still reports `true` per the Javadoc. Check `isClosed()`.

**8. Does a client succeeding in `connect` mean the server has finished processing the request?** No. TCP connect/handshake, accept, and application payload processing are separate stages.

## Authoritative Sources and Further Reading

- [Java SE 17 – ServerSocket Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): constructors, `bind`, `accept`, backlog, `setSoTimeout`, `close`, and state.
- [Java SE 17 – Socket Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): connected socket, `connect`, streams, and read timeout.
- [Java SE 17 – InetSocketAddress Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): IP and port endpoint.
- [Java SE 17 – ServerSocketChannel Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): non-blocking/NIO variant.
- [RFC 9293 – Transmission Control Protocol](https://www.rfc-editor.org/rfc/rfc9293): TCP connection lifecycle and transport mechanics.

**Takeaway:** `ServerSocket` **binds a local address/port → puts the OS into listen mode → `accept()` receives a new `Socket` for each connection**. The listener continues accepting clients, while each accepted socket is responsible for exchanging bytes and closing independently. Distinguishing backlog, `accept` timeout, `read` timeout, IP bind scope, and per-socket lifecycle is the foundation for writing correct TCP servers.
