# Identifying UnknownHostException, BindException, ConnectException, and SocketTimeoutException in Java 17

In the **Configuration and Observability** topic of Java Advance — networking, a developer needs to determine **at which stage** an error occurred before deciding to retry or report an incident. Even though they are all connection errors, **an unresolvable hostname**, **a local port that cannot be bound**, **a remote TCP port refusing a connection**, and **a socket waiting past its deadline** are four very different situations.

Four core exceptions:

- **UnknownHostException:** Java cannot determine the IP address of a hostname during a name resolution attempt.
- **BindException:** the operation of binding a socket to a **local address/port** failed.
- **ConnectException:** the operation of connecting to a **remote address/port** encountered an error, typically connection refused.
- **SocketTimeoutException:** a blocking operation on a socket exceeded the configured deadline; this can occur during **connect**, **accept**, or **read** depending on the API.

**No exception rule proves solely by class that the remote server has stopped running.** You need to examine **class, operation phase, endpoint, timeout policy, OS/network state, and root cause**. A read timeout can happen after the server has already committed business logic; a BindException can be entirely a deployment error on your own machine.

This lesson uses **Java SE 17**, with two complete programs compiled with **javac --release 17** and run successfully on loopback. The theory sections cover the inheritance hierarchy, how to catch them, relationships with HttpClient/CompletableFuture, observability/metrics, retry strategies, and exercises.

## 1. Placing Exceptions in the Right Stage

~~~text
CLIENT
  |
  +-- resolve hostname -> IP
  |       +-- UnknownHostException
  |
  +-- bind local IP:port (if requested)
  |       +-- BindException
  |
  +-- connect remote IP:port
  |       +-- ConnectException (typically refused)
  |       +-- SocketTimeoutException (when connect deadline expires)
  |       +-- NoRouteToHostException / other IOException
  |
  +-- read from an opened connection
          +-- SocketTimeoutException (read timed out)
          +-- -1 from InputStream.read(): EOF, NOT a timeout
          +-- other SocketException/IOException: reset/I/O failure

SERVER
  |
  +-- ServerSocket.bind(local IP:port)
  |       +-- BindException
  |
  +-- ServerSocket.accept()
  |       +-- SocketTimeoutException (accept timeout)
  |
  +-- acceptedSocket.getInputStream().read()
          +-- SocketTimeoutException (read timeout)
~~~

**An API may combine multiple steps**: the Socket(host, port) constructor can resolve and connect in a single call. Java NIO/async APIs also have their own exceptions and states. Do not treat the diagram as a claim that every program always invokes each operation explicitly.

| Exception | Typical step | Check first |
|---|---|---|
| UnknownHostException | DNS/hostname resolution | Hostname, DNS server, hosts file, search domains, container namespace |
| BindException | Local bind | Is the port already in use? Does the local IP exist? Another listener? |
| ConnectException | Remote connect | Are IP/port correct? Is there a listener? Active firewall rejection? |
| SocketTimeoutException | Connect/accept/read timed out | Which exact method, which timeout, is the socket still open? |

## 2. Inheritance Hierarchy and Catch Order

~~~text
java.lang.Exception
  |
  +-- java.io.IOException
  |      |
  |      +-- java.net.UnknownHostException
  |      |
  |      +-- java.net.SocketException
  |      |      +-- java.net.BindException
  |      |      +-- java.net.ConnectException
  |      |      +-- java.net.NoRouteToHostException
  |      |
  |      +-- java.io.InterruptedIOException
  |      |      +-- java.net.SocketTimeoutException
  |      |
  |      +-- java.net.http.HttpTimeoutException
  |             +-- java.net.http.HttpConnectTimeoutException
  |
  +-- java.util.concurrent.TimeoutException
~~~

**BindException and ConnectException are subclasses of SocketException. SocketTimeoutException is NOT a subclass of SocketException:** it extends **InterruptedIOException**. **UnknownHostException** is an IOException, not under SocketException.

If you need to classify them separately:

~~~java
try {
    networkOperation();
} catch (UnknownHostException ex) {
    // DNS/hostname lookup.
} catch (BindException ex) {
    // Bind to local port.
} catch (ConnectException ex) {
    // Connect to remote port.
} catch (SocketTimeoutException ex) {
    // Connect/accept/read timeout: must also know the phase.
} catch (SocketException ex) {
    // Remaining socket errors.
} catch (IOException ex) {
    // Other IOException.
}
~~~

**The snippet above only illustrates the order**; networkOperation is a placeholder name, and the Java compiler may treat specific branches as unreachable if the try block only throws a narrower exception type. In a real catch chain, **do not place IOException before its subclasses**, and do not place SocketException before BindException/ConnectException. For a classifier using instanceof, apply the same check order.

## 3. UnknownHostException: Unable to Determine the IP of a Hostname

The Java 17 Javadoc defines **UnknownHostException** as thrown when the IP address of a host could not be determined.

~~~java
InetAddress result = InetAddress.getByName("service.example.invalid");
~~~

This is an API snippet, not a program with fixed stdout. The .invalid domain is reserved for documentation, but DNS resolvers, VPNs, proxies, hosts files, DNS wildcards, and caches can differ by environment. Do not design a unit test that requires an Internet lookup to always fail after exactly 100 ms.

**Causes to check:** misspelled hostname, service discovery lacking a record, DNS outage, wrong search suffix, container/pod having a different resolver configuration than the host machine, hostname accidentally containing a port, IPv4/IPv6 lookup preference, or internal DNS being unavailable. UnknownHostException **does not tell you for sure whether the remote host is running or not**, because a TCP connect may not have been attempted yet.

To investigate, record the **secrets-redacted hostname**, runtime environment, resolver, DNS records, timestamp, and resolved IPs (if any). Test from the **same network namespace/container**, not just from your laptop. Use InetAddress.getAllByName(host) to observe addresses when resolution succeeds; OS tools like nslookup/dig can provide supplementary information, though their cache/lookup path differs from Java.

**Do not force every NIO API to throw UnknownHostException**. Java NIO channels may use **UnresolvedAddressException** for an unresolved InetSocketAddress. Read the Javadoc of the SocketChannel/AsynchronousSocketChannel you are using.

In the hands-on program below, UnknownHostException is **constructed synthetically** solely to illustrate type classification, without making a DNS query. End-to-end DNS testing should use a controlled DNS test server.

## 4. BindException: Local Address or Port Cannot Be Bound

**BindException extends SocketException** and typically occurs when **ServerSocket.bind(...)** or **Socket.bind(...)** cannot reserve a local IP:port.

~~~java
try (ServerSocket listener = new ServerSocket()) {
    listener.bind(new InetSocketAddress("127.0.0.1", 8080));
}
~~~

The snippet above has implicit imports. If another process already occupies local port 8080 or the bind IP is invalid in the environment, the call may throw BindException. Error messages such as **Address already in use** are OS-dependent; you should not classify by a substring of exception.getMessage().

**Main causes:** another listener holding the port, multiple replicas binding the same port, a restart/shutdown process not yet releasing resources, binding an IP that does not exist on any interface, IPv4/IPv6 wildcard conflicts, or OS socket options/policies. **Client-side sockets** can also encounter BindException if the application explicitly binds a source port that is already occupied.

**How to handle:** check the local address/port, the process, and the network namespace holding the port; verify replicas and startup/shutdown. For tests, use **new ServerSocket(0, backlog, address)** so the OS assigns an ephemeral port and read **getLocalPort()**. **SO_REUSEADDR does not guarantee taking over every port that already has a listener**, although it can help with certain OS-specific reuse/TIME_WAIT policies. A BindException caused by static configuration should usually fail-fast and have the config fixed, rather than retrying the same port indefinitely.

**Do not report BindException as the remote server being offline**: the error occurs when acquiring a **local** resource.

## 5. ConnectException: Unable to Connect to Remote Address/Port

**ConnectException extends SocketException**. According to the Javadoc, it is commonly encountered when a remote host/port **refuses the connection**, for example when no process is listening on that port.

~~~java
try (Socket client = new Socket()) {
    client.connect(new InetSocketAddress(
            "127.0.0.1", 50000), 500);
}
~~~

This is a snippet. There is no guarantee that port 50000 is free on every machine; if a listener is present, it will succeed. If no port is listening and the OS actively refuses, it can throw **ConnectException** very quickly.

**Common causes:** wrong remote port, server not started or restarting, server bound only to loopback, firewall/NAT/LB actively rejecting, service discovery pointing to an old port, connecting to the wrong IPv4/IPv6 interface, or resource limits. ConnectException is not a DNS error: the hostname may resolve to an IP normally, but the **remote port is not accepting**.

Distinguish it from timeouts:

- **Fast refusal**: a rejection signal is received, usually ConnectException.
- **Network drop/no response**: may wait until the connect timeout, or the OS may return another error.
- **No route**: may be NoRouteToHostException/another IOException.
- **DNS failure**: may be UnknownHostException or an API's unresolved error.

**TCP connect success is not HTTP success**. The remote side may accept the connection and then send no bytes, return 500/503, reset, or return an invalid protocol response. If connect succeeds but read times out, the exception class and handling are different.

## 6. SocketTimeoutException: Need to Know Which Operation Timed Out

**SocketTimeoutException extends InterruptedIOException**, and can appear in multiple blocking operations:

| Operation | Deadline configuration | When time expires |
|---|---|---|
| Socket.connect(remote, timeoutMs) | Second parameter of connect | May throw SocketTimeoutException when TCP connect has not completed |
| ServerSocket.accept() | ServerSocket.setSoTimeout(ms) | Times out if no incoming connection has arrived |
| Socket.getInputStream().read() | Socket.setSoTimeout(ms) | Times out if no data has been read |
| DatagramSocket.receive() | DatagramSocket.setSoTimeout(ms) | Times out when no datagram has arrived |

**Socket.setSoTimeout is not a connect timeout**:

~~~java
socket.connect(remoteEndpoint, 2000); // Connect budget.
socket.setSoTimeout(1000);            // Blocking read budget.
int firstByte = socket.getInputStream().read();
~~~

This is a snippet; socket and remoteEndpoint are defined at the caller. **ServerSocket.setSoTimeout** controls **accept**, and does not apply by default to reads on newly accepted Sockets. On an accepted socket, if you want to bound reads, you must configure SO_TIMEOUT on **that socket**.

**A value of 0** in these timeout APIs means no explicit time limit at that API level; the OS can still detect errors and terminate the operation. Avoid waiting indefinitely if the business logic requires a deadline.

### Accept/read timeouts do not automatically close the socket

- After **ServerSocket.accept()** throws SocketTimeoutException due to SO_TIMEOUT, the Javadoc states that the ServerSocket remains valid.
- After **Socket InputStream.read()** times out, the Socket may also remain open; the server could send bytes later.
- **Socket.connect(endpoint, timeout)** is a different phase; when connect fails, you should not assume that socket can be used as a successful connection.

**Read timeout differs from EOF:** read returning **-1** is end-of-stream. Read throwing SocketTimeoutException means the wait timed out, which does not prove the peer has shut down. A reset error may be a different SocketException.

**Read SO_TIMEOUT does not create an overall deadline for the entire response**. If the peer trickles one byte before each read timeout, the read loop can drag on for a long time. You need separate limits on total bytes, a global deadline, and protocol validation.

**Do not set the interrupt flag when catching SocketTimeoutException** just because its superclass is named InterruptedIOException: a timeout does not prove Thread.interrupt occurred.

## 7. Java 17 Program: Simulating and Triggering Real Socket Errors

**SocketFailureLab.java** uses loopback, ephemeral ports, and try-with-resources to:

1. Construct a **synthetic UnknownHostException**; no external DNS dependency.
2. Hold a local port with a first listener, then attempt to bind a second listener → **BindException**.
3. Close a listener on an ephemeral port, then connect to that port → normally **ConnectException**. There is a **very small race** if another process grabs that exact port in the gap.
4. Set ServerSocket SO_TIMEOUT = 150 ms with no client connecting → **SocketTimeoutException on accept**.
5. Establish a TCP connection, send no bytes, set read SO_TIMEOUT = 150 ms → **SocketTimeoutException on read**.
6. Verify that the listener and accepted socket remain open after the timeout.

Create the file **SocketFailureLab.java**:

~~~java
import java.io.IOException;
import java.net.BindException;
import java.net.ConnectException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;

public class SocketFailureLab {
    private static final InetAddress LOOPBACK = InetAddress.getLoopbackAddress();

    private static void bindCollision() throws Exception {
        try (ServerSocket first = new ServerSocket(0, 10, LOOPBACK);
             ServerSocket second = new ServerSocket()) {
            second.setReuseAddress(false);
            try {
                second.bind(new InetSocketAddress(
                        LOOPBACK, first.getLocalPort()));
                throw new AssertionError("Second bind unexpectedly succeeded");
            } catch (BindException expected) {
                System.out.println("Bind: BindException");
            }
        }
    }

    private static void connectRefused() throws Exception {
        int unusedPort;
        try (ServerSocket temporary = new ServerSocket(0, 10, LOOPBACK)) {
            unusedPort = temporary.getLocalPort();
        }
        try (Socket client = new Socket()) {
            try {
                client.connect(new InetSocketAddress(LOOPBACK, unusedPort), 500);
                throw new AssertionError("Unexpected TCP listener on test port");
            } catch (ConnectException expected) {
                System.out.println("Connect: ConnectException");
            }
        }
    }

    private static void acceptTimeout() throws Exception {
        try (ServerSocket server = new ServerSocket(0, 10, LOOPBACK)) {
            server.setSoTimeout(150);
            try {
                server.accept();
                throw new AssertionError("Unexpected incoming connection");
            } catch (SocketTimeoutException expected) {
                System.out.println("Accept: SocketTimeoutException");
                System.out.println("Accept socket still open: " + !server.isClosed());
            }
        }
    }

    private static void readTimeout() throws Exception {
        try (ServerSocket server = new ServerSocket(0, 10, LOOPBACK);
             Socket client = new Socket()) {
            client.connect(new InetSocketAddress(
                    LOOPBACK, server.getLocalPort()), 500);
            try (Socket accepted = server.accept()) {
                accepted.setSoTimeout(150);
                try {
                    accepted.getInputStream().read();
                    throw new AssertionError("Unexpected application bytes or EOF");
                } catch (SocketTimeoutException expected) {
                    System.out.println("Read: SocketTimeoutException");
                    System.out.println("Read socket still open: " + !accepted.isClosed());
                }
            }
        }
    }

    private static void simulatedDnsFailure() {
        // Constructed exception only; no DNS/network request performed.
        IOException failure = new UnknownHostException("synthetic DNS failure");
        if (!(failure instanceof UnknownHostException)) {
            throw new AssertionError("Wrong exception class");
        }
        System.out.println("DNS example (synthetic): UnknownHostException");
    }

    public static void main(String[] args) throws Exception {
        simulatedDnsFailure();
        bindCollision();
        connectRefused();
        acceptTimeout();
        readTimeout();
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 SocketFailureLab.java
java SocketFailureLab
~~~

Stdout from a successful run:

~~~text
DNS example (synthetic): UnknownHostException
Bind: BindException
Connect: ConnectException
Accept: SocketTimeoutException
Accept socket still open: true
Read: SocketTimeoutException
Read socket still open: true
~~~

**Compiled with javac --release 17 and run successfully on the JDK in a loopback environment**, matching all seven lines of output. No external network is used. The DNS exception here is **constructed directly with new**, not a real DNS failure. The refused test depends on the OS having no concurrent listener on that port.

**BindException** is tested while the first socket is still listening; **accept timeout** does not close the ServerSocket; **read timeout** does not automatically close the accepted socket. However, in real code you may **explicitly close** the socket after a timeout if the business deadline has expired or the protocol state is unsafe for further reads.

## 8. Java 17 Program: Classifying Exceptions and Unwrapping Asynchronous Failures

The second program focuses on the **inheritance hierarchy and classification**, without making network requests. All exceptions here are **synthetic**. It distinguishes the four topic groups from HttpClient timeouts and **Future.get(timeout)**.

**NetworkExceptionClassifier.java**:

~~~java
import java.io.IOException;
import java.io.InterruptedIOException;
import java.net.BindException;
import java.net.ConnectException;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpTimeoutException;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeoutException;

public class NetworkExceptionClassifier {
    private static Throwable unwrap(Throwable failure) {
        Throwable current = failure;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    private static String category(Throwable failure) {
        Throwable cause = unwrap(failure);
        if (cause instanceof UnknownHostException) return "DNS";
        if (cause instanceof BindException) return "LOCAL_BIND";
        if (cause instanceof ConnectException) return "REMOTE_CONNECT";
        if (cause instanceof SocketTimeoutException) return "SOCKET_TIMEOUT";
        if (cause instanceof HttpConnectTimeoutException) return "HTTP_CONNECT_TIMEOUT";
        if (cause instanceof HttpTimeoutException) return "HTTP_RESPONSE_TIMEOUT";
        if (cause instanceof TimeoutException) return "CALLER_WAIT_TIMEOUT";
        if (cause instanceof IOException) return "OTHER_IO";
        return "OTHER";
    }

    public static void main(String[] args) {
        Throwable[] examples = {
                new UnknownHostException("synthetic"),
                new BindException("synthetic"),
                new ConnectException("synthetic"),
                new SocketTimeoutException("synthetic"),
                new HttpConnectTimeoutException("synthetic"),
                new HttpTimeoutException("synthetic"),
                new TimeoutException("synthetic"),
                new CompletionException(new ConnectException("synthetic"))
        };
        for (Throwable example : examples) {
            System.out.println(example.getClass().getSimpleName()
                    + " -> " + category(example));
        }
        System.out.println("Bind is SocketException: "
                + (new BindException() instanceof SocketException));
        System.out.println("Connect is SocketException: "
                + (new ConnectException() instanceof SocketException));
        System.out.println("Socket timeout is InterruptedIOException: "
                + (new SocketTimeoutException() instanceof InterruptedIOException));
        System.out.println("HTTP connect timeout is HttpTimeoutException: "
                + (new HttpConnectTimeoutException("synthetic")
                instanceof HttpTimeoutException));
    }
}
~~~

Run commands:

~~~bash
javac --release 17 NetworkExceptionClassifier.java
java NetworkExceptionClassifier
~~~

Verified stdout:

~~~text
UnknownHostException -> DNS
BindException -> LOCAL_BIND
ConnectException -> REMOTE_CONNECT
SocketTimeoutException -> SOCKET_TIMEOUT
HttpConnectTimeoutException -> HTTP_CONNECT_TIMEOUT
HttpTimeoutException -> HTTP_RESPONSE_TIMEOUT
TimeoutException -> CALLER_WAIT_TIMEOUT
CompletionException -> REMOTE_CONNECT
Bind is SocketException: true
Connect is SocketException: true
Socket timeout is InterruptedIOException: true
HTTP connect timeout is HttpTimeoutException: true
~~~

**Compiled with javac --release 17 and run successfully**, matching all 12 lines. The unwrap function extracts the cause from **CompletionException/ExecutionException**, without attempting to strip every kind of wrapper; in production logs, preserve the original stack trace and context layers.

**Placing instanceof IOException at the top of category is wrong** if you want to distinguish subclasses: all specific socket errors would be classified as OTHER_IO. Put specific classes first, and the general fallback last.

## 9. Distinguishing from java.net.http.HttpClient

**HttpClient.Builder.connectTimeout(Duration)** limits establishing a **new** connection; **HttpRequest.Builder.timeout(Duration)** limits waiting for a response to **a single request**. This is a different API from raw Socket.

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
~~~

This is a snippet, assuming uri is valid and imports are present. If opening a new connection is required and does not finish in time, the appropriate error is **HttpConnectTimeoutException**; if the request response is not received in time, **HttpTimeoutException**. **HttpConnectTimeoutException extends HttpTimeoutException**, not SocketTimeoutException.

**HTTP status 408 or 504** is a response from a server/gateway, not automatically equivalent to a client-side Java timeout exception. If you have an HttpResponse, check statusCode; if the exchange failed, inspect the IOException class/cause.

With **sendAsync**, the future can complete exceptionally; **join** wraps the error in CompletionException, while **get** typically wraps it in ExecutionException. Meanwhile, **future.get(timeout, unit)** can throw **java.util.concurrent.TimeoutException** simply because the caller waited too long; it does not prove the HTTP operation was cancelled or that the server did not process it.

### NIO and async sockets

Do not force **SocketChannel** or **AsynchronousSocketChannel** to report the exact same errors as blocking Socket: you may encounter **UnresolvedAddressException, NotYetConnectedException, AlreadyBoundException, ClosedChannelException**, or other exceptions depending on state. When debugging, log the **exact method and channel state**, and do not construct a new exception that hides the root cause.

## 10. Logs, Metrics, and Recovery Decisions

A good log carries **phase**, **exception class**, endpoint alias, and timeout:

~~~text
event=network_failure
phase=connect
target_alias=inventory-service
remote_port=8443
timeout_ms=2000
elapsed_ms=2007
exception_class=java.net.SocketTimeoutException
attempt=2
request_id=redacted
~~~

The lines above are **illustrative**, not an actual measurement. Timeout scheduling can slightly exceed the configured number.

You should also record local IP/port when binding, DNS lookup result when permitted, root cause chain, bytes sent/received, socket lifecycle, and JDK/OS/container details when investigating. Use **System.nanoTime()** to measure elapsed time. Do not log tokens, passwords, Authorization headers, private query strings, or full response bodies. Metrics should attach low-cardinality labels such as exception class, phase, and endpoint alias rather than raw URLs.

### Handling Policy

| Error | Handling approach |
|---|---|
| **UnknownHostException** | Check DNS/host; bounded retry for transient DNS errors; fail-fast for fixed typos |
| **BindException** | Check local IP/port, port-holding process, replicas; do not retry indefinitely with the same config |
| **ConnectException** | Check listener/remote port/proxy/firewall; retry when transient and within deadline |
| **SocketTimeoutException on accept** | Usually can continue accepting or check shutdown flag |
| **SocketTimeoutException on read** | Check partial protocol state, overall deadline, app outcome |
| **SocketTimeoutException on connect** | Check route/drop, retry with backoff if permitted |
| **HttpTimeoutException** | Check request timeout and idempotency |
| **Future TimeoutException** | Caller stopped waiting; decide cancellation/cleanup separately |

A business operation with a 5-second total deadline should not give the first attempt 5 seconds and then retry for another 5 seconds outside the budget. Compute the **remaining deadline** from a single System.nanoTime baseline, and add a retry cap, exponential backoff, and jitter. If a POST command has side effects, a timeout **does not prove the server did not commit**; use an idempotency key or reconciliation instead of blind retries.

## 11. Common Mistakes to Avoid

1. Lumping every IOException together as "remote server down"; BindException can be entirely a local error.
2. Catching SocketException and assuming you have caught SocketTimeoutException; the inheritance hierarchy is not structured that way.
3. Catching IOException/SocketException before specific subclasses.
4. Treating UnknownHostException as always being DNS NXDOMAIN; there are also lookup configuration/cache/transient errors.
5. Treating ConnectException as a name resolution error; the remote port can be refused after DNS succeeds.
6. Treating Socket.setSoTimeout as the timeout for Socket.connect; use the timeout parameter of connect.
7. Assuming an accept timeout automatically closes the listener or a read timeout automatically closes the connected socket.
8. Treating read() returning -1 as SocketTimeoutException; -1 means EOF.
9. Enabling SO_REUSEADDR and assuming BindException can no longer happen.
10. Using an arbitrary public IP to "guarantee" ConnectException or a connect timeout in tests.
11. Comparing exception.getMessage() against English text to determine the error type.
12. Retrying indefinitely after a network failure, causing a retry storm or duplicate side effects.
13. Equating HttpConnectTimeoutException, SocketTimeoutException, and Future TimeoutException.
14. Calling Future.get(timeout) and assuming the underlying network request stops automatically.
15. Logging URLs with secrets or using raw endpoints/user IDs as metric labels.

## 12. Hands-On Exercises

**Exercise A — Catch order:** in NetworkExceptionClassifier, place the IOException check before UnknownHostException and observe all subclasses being grouped into OTHER_IO; fix the order.

**Exercise B — Bind conflict:** hold a listener on an OS-assigned port, then try to bind another listener to the same IP:port. Compare BindException with ConnectException; what is local, and what is remote?

**Exercise C — Accept timeout:** change 150 ms to 300 ms, measure elapsed time with System.nanoTime, and verify that the listener remains open. Do not assert exact millisecond precision.

**Exercise D — Read timeout vs EOF:** establish a connection, first send no bytes so read times out; then try client.shutdownOutput() so read() can return -1. Explain the difference.

**Exercise E — Connect refused:** change the remote port to a port with no listener. Record the class and phase; test a case with a listener to see that connect succeeds while read can still time out.

**Exercise F — DNS lab:** use a DNS test server you control with an existing name and a non-existent name; observe InetAddress.getAllByName and caching, without using Internet DNS as a unit-test oracle.

**Exercise G — Future wrappers:** create CompletableFuture.failedFuture(new ConnectException("synthetic")), call join, then use getCause from CompletionException to classify it correctly.

**Exercise H — HTTP request timeout:** create a localhost HTTP server that returns a slow response, call HttpClient with a short HttpRequest.timeout, and distinguish HttpTimeoutException from raw SocketTimeoutException.

**Exercise I — Overall deadline:** cap all attempts/connect/read/backoff at 3 seconds using a monotonic clock, without resetting the deadline after each retry.

**Exercise J — Idempotency:** simulate a server creating an order and responding late so the client times out; design an idempotency key/reconciliation before retrying.

**Exercise K — Logging:** create a log record containing only phase, class, endpoint alias, timeout, duration, attempt, and correlation ID; verify that no credentials/PII are exposed.

## 13. Review Questions

**1. What does UnknownHostException indicate?** The IP of a host could not be determined during a lookup operation.

**2. Is BindException local or remote?** Local bind.

**3. When is ConnectException typically encountered?** The remote connection is refused or fails while opening TCP.

**4. Can SocketTimeoutException occur during connect?** Yes, with Socket.connect(endpoint, timeout).

**5. What does ServerSocket.setSoTimeout control?** accept().

**6. What does Socket.setSoTimeout control?** Blocking InputStream.read() on the Socket.

**7. What does a timeout of 0 mean?** No explicit deadline at that API level; the OS can still return an error.

**8. Does an accept timeout automatically close the listener?** No, per the contract.

**9. How does a read timeout differ from EOF?** A timeout throws an exception; EOF is read() returning -1.

**10. Does SocketTimeoutException extend SocketException?** No; it extends InterruptedIOException.

**11. What do BindException and ConnectException extend?** SocketException.

**12. Does UnknownHostException prove the remote server is dead?** No.

**13. Does ConnectException prove DNS is wrong?** No.

**14. Why must you know the phase when encountering SocketTimeoutException?** The same class can belong to connect, accept, or read.

**15. Is retrying after a read timeout safe for POST?** Not by default; the server may have already committed.

**16. What does HttpConnectTimeoutException extend?** HttpTimeoutException.

**17. What exception type does CompletableFuture.get(timeout) throw when the wait time expires?** java.util.concurrent.TimeoutException.

**18. Does a Future wait timeout cancel the request?** Not guaranteed.

**19. Why should you not parse the exception message to decide on retries?** Messages depend on the OS/locale/provider.

**20. How does port 0 help in tests?** It asks the OS to choose an ephemeral port, reducing conflicts.

**21. What should you do for deterministic DNS testing?** Synthetic unit tests or a controlled DNS test environment.

**22. Does SO_REUSEADDR fix every BindException?** No.

**23. What should a log contain?** Class, phase, endpoint alias, timeout, elapsed, attempt, and request ID.

**24. What time source should be used to measure elapsed time?** System.nanoTime().

**25. Why does retry logic need an overall deadline?** So multiple attempts do not exceed the business budget.

## 14. Official Java SE 17 Documentation

- UnknownHostException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/UnknownHostException.html
- BindException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/BindException.html
- ConnectException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ConnectException.html
- SocketTimeoutException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html
- SocketException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketException.html
- Socket: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- ServerSocket: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html
- InetAddress: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetAddress.html
- InterruptedIOException: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InterruptedIOException.html
- HttpTimeoutException: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html
- HttpConnectTimeoutException: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html
- CompletableFuture: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html

**Remember:** **UnknownHostException** belongs to the IP resolution phase, **BindException** belongs to local bind, **ConnectException** belongs to remote connect, and **SocketTimeoutException** depends on the connect/accept/read phase and timeout policy. Always examine **exception class + phase + root cause**; do not equate SocketTimeoutException with HttpTimeoutException or Future TimeoutException. Before retrying, check the deadline, side effects, and idempotency; protect socket resources and do not expose sensitive data in logs.