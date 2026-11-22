# SocketChannel.connect(), finishConnect() and Pending Connections in Java NIO

In the **Buffers and Channels** section of Java Networking, **java.nio.channels.SocketChannel** has a very important difference between **blocking** and **non-blocking** modes when establishing a TCP connection. In blocking mode, calling **connect(remote)** waits for the connection to succeed or fail. In non-blocking mode, that call can **initiate** the connection and return **false** immediately: in that case, the SocketChannel is **not yet considered connected** under the Java contract, and you cannot arbitrarily read/write. The application needs to use **finishConnect()**, typically after a **SelectionKey.OP_CONNECT** event, to confirm that the connection has completed or to receive an error.

The three core APIs are **connect(SocketAddress)**, **finishConnect()**, and **isConnectionPending()**; two related checks are **isConnected()** and **isOpen()**. They handle the following scenarios: immediate connection completion, pending connection, connection completion after one or more Selector cycles, failure/timeout, and resource management.

This is foundational knowledge for building an **NIO event loop** that manages multiple TCP connections without dedicating a blocked thread to each connect operation. This lesson uses Java 17+, with runnable examples using localhost and dynamic ports, state error examples, timeout explanations, ByteBuffer, partial I/O, cleanup, and exercises.

## 1. SocketChannel State Model

A newly opened **SocketChannel.open()** is open (**isOpen() == true**) but **not yet connected**. The default mode of the channel is **blocking**. To perform a non-blocking connect, configure it before connecting:

~~~java
SocketChannel channel = SocketChannel.open();
channel.configureBlocking(false);
boolean immediate = channel.connect(remoteAddress);
~~~

The snippet above only illustrates the API: it assumes **remoteAddress** is a valid SocketAddress, imports are present, and the channel must be closed when finished. The variable **immediate** means “the connection completed immediately during connect()” rather than meaning “whether an error occurred or not”.

~~~text
OPEN / UNCONNECTED
       |
       | configureBlocking(false)
       | connect(remoteAddress)
       |
       +---- true -----------------------> CONNECTED
       |                                   isConnected() = true
       |                                   isConnectionPending() = false
       |
       +---- false ---> CONNECTION_PENDING
                           isConnected() = false
                           isConnectionPending() = true
                                     |
                                     | wait for OP_CONNECT
                                     | finishConnect()
                                     |
                         +-----------+------------+
                         |           |            |
                        false       true       IOException
                         |           |            |
                      PENDING     CONNECTED    FAILED/CLOSED
~~~

When a non-blocking connect returns **false**, the kernel has received the request to start connecting, but the application must complete the state transition via **finishConnect()**. Even if the TCP handshake on the machine has already produced a result, **isConnectionPending()** still represents an incomplete progress under the Java API until finishConnect resolves it. Do not treat “TCP looks ready” as sufficient to read/write.

**connect returning true immediately is a normal case**, especially on localhost. Therefore, correct code must handle both the true and false branches; never assume a non-blocking connect will always fire a subsequent OP_CONNECT event.

## 2. Contract of Each Method

| Method | When used with non-blocking SocketChannel | Remember |
|---|---|---|
| **connect(remote)** | Returns true if completed immediately, false if still connecting; may throw an exception | false means pending, not connection failure |
| **finishConnect()** | Returns true if completed; false if not yet completed; IOException on error | Only after true does it enter the I/O state |
| **isConnectionPending()** | True if connect has been initiated but not yet completed via finishConnect | Not a wait command; only an observation |
| **isConnected()** | True when the channel is open and connected | Does not replace checking for future I/O errors |
| **isOpen()** | True if not yet closed | Does not prove it is connected |
| **configureBlocking(false)** | Enables non-blocking connect and Selector registration | Must be called before register/select and connect |

### connect in blocking mode

According to the Java 17 Javadoc, **SocketChannel.connect(remote)** in blocking mode waits until the connection succeeds or an I/O error occurs. A successful connect returns **true**. If you want to handle multiple connections in a single event loop, do not leave SocketChannel in blocking mode and call connect on the event-loop thread.

### connect in non-blocking mode

~~~java
channel.configureBlocking(false);
if (channel.connect(remote)) {
    // CONNECTED immediately: proceed directly to appropriate I/O.
} else {
    // CONNECTION_PENDING: wait and use finishConnect().
}
~~~

**connect(false) is not a ConnectException.** If the server refuses or the network fails, Java may throw an **IOException** immediately during connect or report the error later via finishConnect. There is no rule that every error appears at a specific step.

### finishConnect has three main outcomes

1. **true:** the connection is complete. If the channel is already connected, calling finishConnect also returns true immediately.
2. **false:** the non-blocking connection is still pending; keep waiting, do not read/write.
3. **IOException:** the connection failed, e.g., the remote refused or a network error occurred. Under the Java 17 contract, a connection attempt that fails via a checked exception **closes the channel**; clean up registration/state and create a new channel when retrying.

**NoConnectionPendingException** occurs when calling finishConnect on a channel that is not connected and has never initiated a connection. This is an operation-order error. Calling **connect()** a second time while pending throws **ConnectionPendingException**; calling connect again on an already connected channel throws **AlreadyConnectedException**.

## 3. Do Not Confuse open, connected, and pending

| Point in time | isOpen | isConnected | isConnectionPending | Next step |
|---|---:|---:|---:|---|
| SocketChannel.open() just returned | true | false | false | configure mode, connect |
| connect(false) | true | false | true | wait for OP_CONNECT/finishConnect |
| finishConnect(false) | true | false | true | continue waiting |
| connect(true) | true | true | false | read/write per protocol |
| finishConnect(true) | true | true | false | update interest ops then I/O |
| connect attempt threw checked exception indicating failure | false per contract | false | false | cleanup, open a new channel if needed |
| close() has been called | false | false | false | do not reuse |

**isConnectionPending() == false is not enough to conclude the connection succeeded.** It is also false on a newly opened unconnected channel and on a closed channel. You must combine it with **isConnected()** and application state.

**SocketChannel.isConnected() differs from java.net.Socket.isConnected():** according to the Java 17 documentation, SocketChannel.isConnected() returns true only when the channel is still **open and connected**. The classic API's Socket.isConnected() can still return true after close because it reflects whether it was ever connected historically. When working with NIO, rely on SocketChannel's own state and I/O results; do not mix the two methods.

**Cannot use isConnectionPending as a wait loop:** calling while(isConnectionPending()) continuously will cause a busy-spin; the state still needs to be completed via finishConnect. Use a Selector or a wait mechanism with a deadline.

## 4. Waiting for OP_CONNECT with Selector

**Selector** monitors the readiness state of multiple **SelectableChannel**s, where SocketChannel uses the flags **OP_CONNECT**, **OP_READ**, and **OP_WRITE**. A channel registered with a Selector must be in non-blocking mode.

Correct procedure:

1. Open **SocketChannel** and **Selector**; switch the channel to non-blocking.
2. Call **connect(remote)**. If it returns true, register **OP_READ**/**OP_WRITE** according to the application's next step—**OP_CONNECT is not needed**.
3. If connect returns false, **register(selector, SelectionKey.OP_CONNECT)**.
4. The event loop calls **selector.select(timeout)** and iterates over **selectedKeys()**.
5. When **key.isConnectable()**, call **channel.finishConnect()**:
   - true: the channel is connected, change **interestOps** to OP_READ/OP_WRITE if needed.
   - false: keep watching OP_CONNECT, wait for the next cycle.
   - IOException: close the channel, cancel the key, clean up state, and report the error.
6. After processing a selected key, call **iterator.remove()** so stale notifications are not retained.
7. If the **connection deadline** expires, close the channel and clean up registration.

~~~text
non-blocking connect(remote)
  |
  +-- true --> CONNECTED --> interestOps(OP_READ or OP_WRITE)
  |
  +-- false -> register(OP_CONNECT)
                |
             select(...)
                |
          isConnectable()
                |
          finishConnect()
                |
       +--------+----------+
       |        |          |
     false     true      IOException
       |        |          |
  keep waiting change ops close/cleanup
~~~

**isConnectable() is only a readiness hint.** According to Java 17 SelectionKey, connectable can mean the connect operation **is ready to complete or has a pending error**. Do not infer that the connection succeeded when Selector returns an OP_CONNECT key; success/incomplete/failure must be distinguished via **finishConnect()**.

**OP_CONNECT must be removed after connecting.** Keeping that flag or continuing to process the key as CONNECTING is a state-machine bug. Once connected, only enable **OP_WRITE** if there is actually data to send; sockets are usually writable almost continuously, so leaving OP_WRITE enabled unconditionally can make the event loop spin busily.

## 5. Complete Java 17 Program: Non-Blocking Connect and Receiving a Reply

This example creates its own **ServerSocketChannel on loopback with a dynamic port**, requiring no Internet connection or external service. The server-side worker thread calls accept, sends the two UTF-8 bytes **OK**, and closes the accepted channel. The client side uses a non-blocking SocketChannel and Selector to connect, waits for finishConnect if needed, and then reads all two bytes.

**Important:** the code handles both **connect(true)** and **connect(false)**, because on localhost behavior depends on OS/timing; the output only prints the final state for stability.

File **NonBlockingConnectDemo.java**:

~~~java
import java.io.EOFException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class NonBlockingConnectDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(loopback, 0));
            ExecutorService workers = Executors.newSingleThreadExecutor();

            try {
                Future<Void> task = workers.submit(() -> {
                    try (SocketChannel peer = server.accept()) {
                        ByteBuffer reply = ByteBuffer.wrap(
                                "OK".getBytes(StandardCharsets.UTF_8));
                        while (reply.hasRemaining()) {
                            peer.write(reply);
                        }
                    }
                    return null;
                });

                boolean connected;
                boolean pending;
                String text;

                try (Selector selector = Selector.open();
                     SocketChannel client = SocketChannel.open()) {
                    client.configureBlocking(false);
                    boolean immediate =
                            client.connect(server.getLocalAddress());

                    SelectionKey key = client.register(
                            selector, immediate
                                    ? SelectionKey.OP_READ
                                    : SelectionKey.OP_CONNECT);

                    ByteBuffer buffer = ByteBuffer.allocate(2);
                    long deadline = System.nanoTime()
                            + TimeUnit.SECONDS.toNanos(5);

                    while (buffer.hasRemaining()) {
                        long leftNanos = deadline - System.nanoTime();
                        if (leftNanos <= 0) {
                            throw new SocketTimeoutException(
                                    "Connect/read deadline expired");
                        }

                        // select(0) waits indefinitely, so use a minimum of 1 ms.
                        long waitMillis = Math.max(
                                1L, TimeUnit.NANOSECONDS.toMillis(leftNanos));
                        selector.select(waitMillis);

                        Iterator<SelectionKey> it =
                                selector.selectedKeys().iterator();

                        while (it.hasNext()) {
                            SelectionKey ready = it.next();
                            it.remove();

                            if (!ready.isValid()) {
                                continue;
                            }

                            if (ready.isConnectable()) {
                                if (client.finishConnect()) {
                                    ready.interestOps(SelectionKey.OP_READ);
                                }
                            }

                            if (ready.isReadable()) {
                                int n = client.read(buffer);
                                if (n == -1) {
                                    throw new EOFException(
                                            "EOF before 2 bytes received");
                                }
                                // n == 0: no bytes available yet, wait for next time.
                            }
                        }
                    }

                    connected = client.isConnected();
                    pending = client.isConnectionPending();
                    buffer.flip();
                    text = StandardCharsets.UTF_8
                            .decode(buffer).toString();
                }

                task.get(5, TimeUnit.SECONDS);
                System.out.println("Connected: " + connected);
                System.out.println("Pending: " + pending);
                System.out.println("Reply: " + text);
            } finally {
                workers.shutdownNow();
            }
        }
    }
}
~~~

Commands to run with Java 17 or later:

~~~bash
javac -encoding UTF-8 NonBlockingConnectDemo.java
java NonBlockingConnectDemo
~~~

Stdout on a successful run:

~~~text
Connected: true
Pending: false
Reply: OK
~~~

### Exact Explanation

- **server.bind(..., 0)** picks an available port on loopback. **server.getLocalAddress()** provides the actual server address to the client.
- **ServerSocketChannel.accept()** is blocking in the worker and does not block the client event loop; the accepted SocketChannel has its own lifecycle.
- **client.configureBlocking(false)** is called before connect. When immediate=true, it registers OP_READ directly; when false, it registers OP_CONNECT and waits for finishConnect.
- **Selector.select(waitMillis)** can return 0 due to timeout or wakeup, so each loop iteration re-checks the deadline instead of immediately concluding an error.
- When ready.isConnectable(), only after **finishConnect(true)** does it change interestOps to OP_READ. If finishConnect is false, the key keeps watching OP_CONNECT; if it throws IOException, try-with-resources cleans up the channel.
- The server sends two bytes **OK**. The client reads until it has both bytes, accepts read() returning 0, and recognizes **-1 before two bytes** as incomplete data.
- **buffer.flip()** switches the ByteBuffer from writing bytes into it to reading/decoding from it. **Future.get()** confirms the server worker finished before printing the three lines.

This is a **minimal connect and I/O demo**, not a production protocol: receiving variable-length responses requires message framing and byte limits; writing multiple ByteBuffers requires handling partial writes and OP_WRITE. The 5-second timeout protects the client wait loop in the example, and does not guarantee that DNS, TLS handshake, or all application business operations fit within 5 seconds.

If binding or connecting to loopback fails, or the machine is too slow, the example may throw an exception/timeout instead of printing the three lines. It does not print a fixed **immediate** value because that depends on runtime conditions.

## 6. Java 17 Example: Initial State and Out-of-Order Call Errors

**finishConnect does not open a new connection on its own.** On a freshly opened channel with no pending connect, calling finishConnect encounters **NoConnectionPendingException**; attempting to read before connecting encounters **NotYetConnectedException**.

File **ConnectionStateDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.channels.NoConnectionPendingException;
import java.nio.channels.NotYetConnectedException;
import java.nio.channels.SocketChannel;

public class ConnectionStateDemo {
    public static void main(String[] args) throws Exception {
        try (SocketChannel channel = SocketChannel.open()) {
            channel.configureBlocking(false);

            System.out.println("Open: " + channel.isOpen());
            System.out.println("Connected: " + channel.isConnected());
            System.out.println("Pending: "
                    + channel.isConnectionPending());

            try {
                channel.finishConnect();
            } catch (NoConnectionPendingException ex) {
                System.out.println(
                        "finishConnect: NoConnectionPendingException");
            }

            try {
                channel.read(ByteBuffer.allocate(1));
            } catch (NotYetConnectedException ex) {
                System.out.println(
                        "read: NotYetConnectedException");
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConnectionStateDemo.java
java ConnectionStateDemo
~~~

Output:

~~~text
Open: true
Connected: false
Pending: false
finishConnect: NoConnectionPendingException
read: NotYetConnectedException
~~~

The output proves **open != connected**, **not pending != connected**, and **finishConnect != connect**. The program uses no network endpoint, so the result does not depend on TCP handshake speed.

## 7. Deadline for Non-Blocking Connect

SocketChannel does not have a **connect(remote, timeout)** overload like some calls on **java.net.Socket**. If connect is pending, the program must track the total wait time itself using **Selector + deadline**.

~~~text
end = monotonicNow + timeoutBudget
connect(remote)
while connection pending:
    remaining = end - monotonicNow
    if remaining <= 0: close channel, report timeout
    selector.select(roundedUpMillis(remaining))
    if OP_CONNECT: finishConnect()
~~~

This is an illustrative algorithm, not standalone runnable Java code.

**Why use System.nanoTime()?** It is suitable for measuring elapsed time and computing relative deadlines; wall-clock time from System.currentTimeMillis() can jump due to NTP or clock adjustments. When converting nanoseconds to milliseconds, do not pass 0 to **Selector.select(0)** because **0 means wait indefinitely**. If you need to select immediately without blocking, use **selectNow()**; if there is still a very short positive deadline remaining, use **at least 1 ms**.

**Selector.select(timeout) does not automatically fail the TCP connect on timeout.** It only ends *one readiness wait*; you must check the deadline of the specific connection and then **close** the incomplete channel. Handle cases where select returns 0, wakeups, and spurious events; do not reset the overall deadline every time an unrelated event is received.

**DNS can be a blocking step before connect.** Creating an InetSocketAddress from a hostname can trigger name resolution before the non-blocking connect call. If the system needs an end-to-end SLA, account for DNS, TCP connect, TLS, auth, and request/response, or use a separate name-resolution mechanism.

**Do not blindly use channel.socket().connect(endpoint, timeout) as a replacement** on a SocketChannel that is in non-blocking mode and registered with a Selector. That is a different API with blocking-mode constraints; inappropriate usage can throw **IllegalBlockingModeException**. Choose one consistent model: when using a Selector, manage deadlines in the event loop and complete the connect via finishConnect.

### How to Track Deadlines for Hundreds of Channels?

Each connection needs its own state: **phase CONNECTING/CONNECTED**, **startedNanos/deadlineNanos**, **SelectionKey**, and its own result callback/future. The event loop chooses the wait duration based on the nearest deadline; after each select, it processes both selected keys and expired connections. Do not use a single deadline variable as a shared timeout for all channels opened at different times.

**Retrying on expiration:** clean up the old channel, cancel the key, notify the caller, and if business logic requires, create a **new SocketChannel** after backoff and within the allowed total budget. Do not keep hundreds of pending channels indefinitely because each channel still consumes a file descriptor and kernel resources.

## 8. ByteBuffer and Post-Connect I/O

Before **connect(true)** or **finishConnect(true)**, the channel is not connected and read/write can throw **NotYetConnectedException**. After connecting, non-blocking I/O still produces partial results:

| Operation | Result | Meaning |
|---|---|---|
| read(dst) | positive number | that many bytes received into ByteBuffer |
| read(dst) | 0 | no bytes currently available, not EOF |
| read(dst) | -1 | end-of-stream on the receive side |
| write(src) | positive number | that many bytes transferred from src to socket |
| write(src) | 0 | cannot send more right now, keep src to retry when writable |

**One read does not equal one message**—TCP is a byte stream. To receive a complete message, you need framing such as length-prefix, delimiter, or an EOF-based protocol. **ByteBuffer.flip()** switches from writing into the buffer to reading from it; **compact()** helps retain unprocessed bytes when receiving more; calling **clear()** on a buffer containing unsent data can lose the payload.

Illustrative example with a connected channel:

~~~java
ByteBuffer outgoing = StandardCharsets.UTF_8.encode("PING");
while (outgoing.hasRemaining()) {
    int n = channel.write(outgoing);
    if (n == 0) {
        // Non-blocking: wait for OP_WRITE then finish writing;
        // DO NOT drop outgoing while data still remains.
        break;
    }
}
~~~

This is not a standalone runnable program; it requires imports, an already-connected channel, and code to manage OP_WRITE after break. While data remains, enable OP_WRITE. Once everything is sent, clear OP_WRITE to avoid a busy loop since sockets are writable almost continuously.

A key can **attach** a state object containing phase, pending output buffer, incoming parser, deadline, and request context. That is a better model than sharing a single ByteBuffer across thousands of connections.

## 9. Exceptions to Remember

| Exception | When? | How to handle |
|---|---|---|
| **NoConnectionPendingException** | finishConnect on a channel that is not connected and not pending | Fix state flow; connect first |
| **ConnectionPendingException** | calling connect again while non-blocking connect is still pending | Do not call connect twice; call finishConnect |
| **AlreadyConnectedException** | calling connect again when already connected | Use I/O, do not reconnect |
| **NotYetConnectedException** | read/write or shutdown when not yet connected | Wait for connect(true)/finishConnect(true) |
| **UnresolvedAddressException** | remote InetSocketAddress is unresolved | Handle domain name resolution |
| **ClosedChannelException** | operation on a closed channel | Cleanup and open a new channel if retrying |
| **IOException**, possibly including ConnectException | Connection refused or network error | Cleanup, log cause, retry with limits |
| **AsynchronousCloseException** | another thread closed the channel during an operation | Coordinate cancellation/ownership |
| **ClosedByInterruptException** | interrupt during interruptible I/O closes the channel | Preserve interrupt policy, cleanup |
| **IllegalBlockingModeException** | incompatible blocking mode/Selector usage | Do not change mode improperly while registered |
| **Selector.select() == 0** | timeout, wakeup, or no ready keys yet | Check deadline, do not assume failure by default |

**Connect errors can appear at connect() or finishConnect().** Specifically, **OP_CONNECT readiness may signal an error that must be extracted via finishConnect()**; do not print “connected” based solely on isConnectable().

According to the Javadoc, if a connect attempt throws a **checked exception** indicating failure, the SocketChannel will **be closed**. Do not retry immediately on that same object; open a new channel. Specific TCP states and error messages may differ between Linux/Windows and depending on firewall/network.

## 10. Common Pitfalls

### 10.1. Handling Only the connect(false) Branch

This is a bug that easily passes tests on one OS and fails on another. **connect(true)** is completely valid, especially when the remote is on localhost; you must proceed directly to protocol I/O and register the new interest.

### 10.2. Busy-Spinning finishConnect

Avoid the following in an event loop:

~~~java
while (!channel.finishConnect()) {
    // No Selector, deadline, or sleep.
}
~~~

It can consume CPU, block other connections, and has no timeout control. Use **OP_CONNECT**, select with a timeout, and complete on the appropriate event.

### 10.3. Confusing OP_CONNECT with Success

Selector indicates that the connect sequence **has a result** or **has an error to handle**; **finishConnect** is what actually provides the outcome. Do not switch the key to OP_READ if finishConnect is still false or throws an exception.

### 10.4. Keeping OP_WRITE Enabled Permanently

In many systems, writable is a constant state. If the event loop has no outgoing ByteBuffer yet keeps OP_WRITE enabled, the selector will wake continuously. Once all data is written, clear the OP_WRITE interest and only re-enable it when there are bytes to send.

### 10.5. Not Removing Selected Keys

After processing selectedKeys, use **iterator.remove()** or an equivalent key-removal operation. Otherwise, the next iteration may keep seeing the old key and process readiness at the wrong time. **SelectionKey.cancel()** also does not necessarily remove the object immediately; the selector processes cancelled keys during a selection pass.

### 10.6. Switching to Blocking While Still Registered

If a channel is still registered with a Selector, calling **configureBlocking(true)** can throw IllegalBlockingModeException. Design a clear registration lifecycle before switching models or continue using non-blocking consistently.

### 10.7. Races When Multiple Threads Manage One Connection

SocketChannel supports concurrent reading and writing within certain API limits, but **connect() and finishConnect() are synchronized with each other**. Do not let multiple threads contend over the state machine, interestOps, and close. Having a single event-loop owner per channel makes it easy to guarantee event ordering. If a worker needs to change interest, pass a thread-safe message and use **Selector.wakeup()** when appropriate.

### 10.8. Not Limiting Pending Channels

Non-blocking does not mean infinite resources. Each channel has a file descriptor, kernel state, deadline, and Java objects. Limit pending counts per endpoint and total concurrent connections, use retry backoff, and close expired ones.

## 11. TCP Connected Does Not Mean the Application Is Ready

**finishConnect(true)** only confirms that the network socket is connected. With TLS, a TLS handshake is still required; with HTTP, a properly formatted request must be sent and the response read; with custom protocols, authentication/session negotiation may still be required.

~~~text
DNS_RESOLVED
    -> TCP_CONNECTING
    -> TCP_CONNECTED
    -> TLS_HANDSHAKING (if any)
    -> APPLICATION_HANDSHAKING / AUTHENTICATING (if any)
    -> READY_FOR_APPLICATION_DATA
    -> CLOSING / CLOSED
~~~

**Do not use isConnected() as an absolute liveness check.** The peer may lose network connectivity immediately after the connection succeeds; subsequent I/O can still fail. Handle EOF, IOException, deadlines, and heartbeats according to the protocol.

If connect fails or times out and the caller wants to retry, open a new channel. For operations with side effects, do not automatically replay application requests when you do not know whether the previous attempt was already processed; you need an idempotency policy and request IDs at the application layer.

## 12. Comparing Java Connection Models

| Criterion | Blocking SocketChannel | Non-blocking SocketChannel + Selector | AsynchronousSocketChannel |
|---|---|---|---|
| connect | Blocks until success/error | Can return true or false immediately | Completion Future/callback |
| Completing connection | No separate finishConnect needed after successful connect | finishConnect when pending | Result via completion API |
| Waiting mechanism | Thread calling connect | OP_CONNECT + Selector + deadline | Completion framework and separate lifecycle |
| I/O | Blocking if mode is kept | Partial I/O, read/write may return 0 | Completion-based read/write |
| Common pitfalls | Long blocking, missing timeout | Forgetting finishConnect, interest, deadline | Callback races, cancellation, state management |

**AsynchronousSocketChannel does not use the same connect/finishConnect pair as SocketChannel.** It is a different API. When using Java 21+ virtual threads, blocking code can be more convenient for many connections in some workloads, though it does not eliminate deadlines, FD limits, or TCP errors.

## 13. Practice Exercises

**A. Observe the immediate/pending branch.** Run NonBlockingConnectDemo multiple times, adding logs for connect's return value and isConnectionPending right afterward. One machine might only show one branch; explain why the code must still handle both.

**B. Skip finishConnect.** In the isConnectable branch, try switching interest to OP_READ without calling finishConnect. Note the risk of NotYetConnectedException, then fix it.

**C. Connection refused.** Test a loopback address/port with no listener in a self-controlled environment. Catch IOException on both connect and finishConnect; log the exact reason, close, and do not expect the same exception subclass or failure timing across all OSes.

**D. Deadline exceeded.** Use a slow-responding test endpoint and cap the connection at 100 ms. Verify that select(0) is not called while a positive deadline remains and that the channel is closed when expired. Do not test against unauthorized third-party networks.

**E. Sending a large ByteBuffer.** After finishConnect(true), send a payload larger than the send buffer. Handle write returning 0, preserve position, register OP_WRITE, and disable OP_WRITE when finished sending; have the server use framing to read all bytes.

**F. Multiple concurrent connections.** Manage 100 pending SocketChannels in one Selector with per-channel state objects/deadlines, limit total FDs, and collect statistics on immediate, pending, success, timeout, and failure counts.

## 14. Self-Check Questions

**1. Does non-blocking connect() returning false mean failure?** No; a connection operation has been initiated and is not yet complete.

**2. If connect() returns true, do we need to wait for OP_CONNECT?** No, it is already connected; move on to I/O.

**3. Does isConnectionPending() always reflect that the kernel is still performing the TCP handshake?** No; it describes a connection not yet completed via the Java API, which may already have a result waiting for finishConnect.

**4. Does key.isConnectable() guarantee the TCP connect succeeded?** No; a failed result can also make the key connectable. Call finishConnect.

**5. What does finishConnect() returning false mean?** The connection is still pending in non-blocking mode; do not read/write yet.

**6. What happens if you call finishConnect without calling connect first?** NoConnectionPendingException when the channel is not connected and has no pending operation.

**7. Does isOpen() being true mean it is connected?** No. A newly created channel is open but not yet connected.

**8. Why does read/write before connecting cause an error?** The SocketChannel is not yet connected; it can throw NotYetConnectedException.

**9. Does Selector.select(0) mean do not wait?** No. It can wait indefinitely; to not wait, use selectNow().

**10. Should OP_CONNECT be kept after finishConnect(true)?** No; change interest to OP_READ or OP_WRITE if needed.

**11. Can you retry connect with the same channel after a checked IOException?** No: per the API, a failed connection attempt may close the channel; create a new channel and manage backoff.

**12. Does connected mean HTTP/TLS is ready?** Not yet; TCP connected is one stage, followed by handshakes and application protocol.

## References

- **Java SE 17 — SocketChannel:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html
- **Java SE 17 — Selector:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html
- **Java SE 17 — SelectionKey:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html
- **Java SE 17 — ByteBuffer:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html

**Remember:** **connect(true)** means immediately connected; **connect(false)** means **pending, not failure**. Only use the channel for I/O after **connect(true)** or **finishConnect(true)**. **OP_CONNECT** signals a situation where the result must be checked via finishConnect, not proof of success. Manage **deadlines, SelectionKey interestOps, ByteBuffer, IOException, close/cancel, and retries** with a clear state machine.