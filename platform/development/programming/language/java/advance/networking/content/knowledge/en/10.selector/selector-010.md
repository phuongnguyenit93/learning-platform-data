# Key Cancellation, EOF Handling, and Closing Connections on Error

## 1. The Problem: Selector Does Not Automatically Close Every Connection

In Java NIO, a **Selector** allows a single thread to monitor multiple **SelectableChannel** instances. A **ServerSocketChannel** typically registers **OP_ACCEPT** to accept connections; each **SocketChannel** after accept registers **OP_READ**, and can then switch to **OP_WRITE** when it needs to send a response. A **SelectionKey** object represents the registration of a channel with a selector and stores interest, readiness, and attachment information.

A server might handle normal clients fine but leak sockets, retain invalid keys, or spin CPU when a client closes a connection, sends malformed data, or an I/O operation throws an exception.

Key distinctions to make:

- **SelectionKey.cancel():** marks the key invalid immediately and requests deregistration from the selector. This is **not SocketChannel.close()**, so it is not enough to release the socket.
- **SocketChannel.close():** closes the channel/socket itself. If the channel is registered with a selector, the associated registration keys are also cancelled, though connection state still needs to be cleaned up.
- **Selector.close():** closes the selector and cancels the associated keys. It **does not automatically close every channel** that was ever registered; the server must close the SocketChannel and ServerSocketChannel instances it owns.
- **iterator.remove() on selectedKeys():** removes the key from the set of keys selected in the current cycle; this is **not key.cancel()**.

A proper cleanup path when a connection ends is to **stop tracking the key, close the channel, and clean up state**. An error on one SocketChannel should generally be isolated to that client; it must not automatically bring down the shared selector.

~~~text
ServerSocketChannel --register(OP_ACCEPT)--> Selector
                                               |
                                             select()
                                               |
                                           selectedKeys()
                                               |
                        +----------------------+----------------+
                        |                      |                |
                     OP_ACCEPT               OP_READ          OP_WRITE
                        |                      |                |
                 accept SocketChannel    read() n>0, 0,-1   write pending
                        |                      |                |
                  register(OP_READ)    EOF or per-conn error    |
                                               |                |
                                      key.cancel + channel.close
                                               |
                                  event loop still serves other clients
~~~

## 2. Registration Lifecycle and Key Sets in Selector

### 2.1. Key APIs

| Object/API | Meaning |
| --- | --- |
| **Selector.open()** | Opens a selector |
| **channel.configureBlocking(false)** | Prerequisite for registering a channel with a selector |
| **channel.register(selector, ops, attachment)** | Creates/updates a key; attaches per-connection state |
| **selector.select()** | Waits for at least one readiness change, wakeup, or related event |
| **selector.selectedKeys()** | The set of keys the event loop needs to process in the current selection cycle |
| **selector.keys()** | The set of keys currently registered with the selector, including uncleaned cancelled state |
| **key.isValid()** | Checks that the key has not been cancelled and the channel/selector are still open |
| **key.interestOps(...)** | Updates the operations of interest while the key is still valid |
| **key.cancel()** | Key becomes invalid immediately; deregistration cleanup is processed later |
| **selector.wakeup()** | Wakes up a waiting select; does not replace close() |

The common readiness bits are **OP_ACCEPT**, **OP_CONNECT**, **OP_READ**, and **OP_WRITE**. Not every operation is valid for every channel: ServerSocketChannel uses OP_ACCEPT; SocketChannel uses operations appropriate for a connected socket.

**Note:** A single readiness event does not guarantee that an entire message is available, nor does it mean a single write will consume the entire ByteBuffer. This is still a TCP byte stream; the parser and outbound queue must manage partial reads/writes.

### 2.2. Selected Keys Must Be Removed from the Selected-Key Set

Common loop pattern:

~~~java
// Structural illustration; selector and handlers are declared in the server.
selector.select();
Iterator<SelectionKey> it = selector.selectedKeys().iterator();

while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove(); // Do not leave old selected keys around for the next cycle.

    if (!key.isValid()) {
        continue;
    }
    // Handle accept/read/write...
}
~~~

**selector.selectedKeys() does not automatically remove a key after your code finishes handling it**. Omitting iterator.remove() can cause the event loop to reprocess stale readiness or spin uselessly.

### 2.3. Cancellation Has Its Own Timing and Scope

Per the SelectionKey contract, calling **key.cancel()** makes the key **immediately invalid**. Removal of the registration from the selector's key set happens during subsequent selection operations. Therefore, you should not use **selector.keys().size() immediately after cancel()** as proof that all channels have been cleaned up.

After cancellation, operations that read or modify readiness/interest such as **key.interestOps(...)** or **key.readyOps()** may throw **CancelledKeyException**. Stop operating on any key that is no longer valid.

An illustrative cleanup:

~~~java
// Illustrative only, not a standalone program.
// Connection resources are owned by the event loop.
static void closeClient(SelectionKey key) throws IOException {
    key.attach(null);       // Drop state reference if appropriate.
    key.cancel();           // Cancel registration.
    key.channel().close();  // Release the underlying channel.
}
~~~

A production implementation needs to handle **errors during close itself**, **repeated cleanup calls**, and other resources held inside the attachment. Calling attach(null) drops the reference, but does not automatically close AutoCloseable resources inside the state; they must be managed separately.

## 3. Handling read() = -1, 0, and Positive Values

With a SocketChannel reading into a ByteBuffer:

~~~java
int n = socketChannel.read(inbound);
~~~

| Value | Correct Interpretation | Possible Action |
| --- | --- | --- |
| **n > 0** | Received n bytes, which may be a partial frame or multiple frames | Switch buffer to read mode, process complete frames, retain incomplete bytes |
| **n == 0** | No bytes received in this call; common in non-blocking mode or when the buffer has no space left | Do not treat as EOF; wait for the next event or handle a full buffer |
| **n == -1** | End of stream (EOF); the peer has closed its sending side and all prior bytes have been read | Check whether the protocol still has outbound data to send; close connection if done |
| **IOException** | Broken I/O | Log and close the connection according to policy |

**Read returning 0 is not EOF.** In non-blocking mode, there may simply be no new bytes at the moment of the call. Wait for the next **OP_READ** instead of closing the connection or spinning infinitely. If the ByteBuffer is already full, do not repeatedly call read with remaining=0; decode frames, expand within a bound, or reject oversized data.

**Read returning -1 is EOF on the receive side**, which does not necessarily mean both directions of TCP are immediately closed. TCP allows **half-close**: the client calls **shutdownOutput()** (FIN on its sending side) while still being able to read the server's response.

- If the server is reading an incomplete length-prefix/body message and hits EOF: the frame is truncated; report an error and clean up the connection.
- If the protocol specifies **reading until EOF** marks the end of the request and **only then does the server send the response**, the server can switch to OP_WRITE and close after finishing the write.
- If there are no valid requests/responses left to process, cancel the key and close the SocketChannel immediately.

Avoid leaving a SocketChannel that has reached EOF in **OP_READ** without changing anything. It may keep being selected as ready-to-read because read will continue returning -1, causing a **busy loop**.

### EOF Does Not Mean a Valid Message

For example, if the protocol requires a 100-byte body but only 70 bytes were received before EOF: it must not be processed as a complete message. If a read returns n > 0, there may still be an incomplete frame. EOF is **stream** lifecycle information, whereas message boundaries are defined by the **application protocol**.

## 4. Isolating Exceptions per Connection

A Selector event loop typically handles many sockets in a single thread. If just one client sends a malformed command and the handler throws an IOException, the server should not needlessly close the entire selector.

| Situation | Handling Scope |
| --- | --- |
| **SocketChannel.read/write IOException** | Usually a single-connection error; close that SocketChannel |
| **Malformed frame, oversized frame, or invalid command** | Reject the request, close the associated socket |
| **CancelledKeyException** when touching an invalid key | Check key lifecycle, stop processing that key |
| **Client EOF** | Per protocol, close immediately or flush remaining outbound data then close |
| **ServerSocketChannel.accept() failure** | May be a server-level listener error; do not disguise it as a bad request |
| **Selector closed/corrupted** | Stop the event loop in a controlled manner, clean up held channels |
| **Serious JVM error** | Do not swallow arbitrarily and assume the server is still safe |

A simple handling layout:

~~~java
// Illustrates the idea; acceptClient/readClient/writeClient/closeClientBestEffort
// are application methods, not built-in APIs.
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();
    if (!key.isValid()) {
        continue;
    }

    try {
        if (key.isAcceptable()) {
            acceptClient();
        } else if (key.isReadable()) {
            readClient(key);
        } else if (key.isWritable()) {
            writeClient(key);
        }
    } catch (IOException | RuntimeException ex) {
        if (key.channel() instanceof SocketChannel) {
            closeClientBestEffort(key); // Only the failing connection.
        } else {
            throw ex; // Listener error that must be handled at the server level.
        }
    }
}
~~~

In production, log the **root error**, connection ID, and any cleanup error if one occurs. If close() throws an exception as well, do not let the cleanup exception mask the real cause. A broad catch block does not replace error classification and resource cleanup.

### Ownership Concerns

- After **accept()**, the new socket is owned by the accept loop until it is successfully registered/handed off.
- If **configureBlocking/register fails**, the accept loop must close the unmanaged SocketChannel.
- Once the connection is registered, the event loop (or connection-management component) is responsible for closing it, cleaning up the attachment, and updating metrics.
- On shutdown, closing the listener does not automatically close all previously accepted SocketChannels.
- Cleanup should be **idempotent**: calling it again should not double-count or produce spurious errors.

## 5. Runnable Java 17+ Example: Key Cancellation, EOF, BAD Error, and Cleanup

The **SelectorCleanupDemo.java** example includes both a Selector-based server and client test code in the same JVM. No Maven, JUnit, or Internet access is needed.

Deterministic scenario:

1. The server opens a **Selector** and a **non-blocking ServerSocketChannel** on **loopback**, with an OS-assigned port.
2. The first client sends **PING + LF**, the server receives it, replies with **PONG + LF**, and closes the socket per the one-request/response-per-connection protocol.
3. The second client calls **shutdownOutput()**, causing the server to encounter **read = -1**. With no pending response, the server closes the socket.
4. The third client sends **BAD + LF**. The handler throws **IOException**, the per-key catch block cancels the key and closes the SocketChannel; the client reads EOF.
5. The fourth client sends **PING** after the BAD error; it receives PONG properly, proving the selector is still operational.
6. The test verifies **4 accepted, 2 PING responses, 1 EOF, 1 malformed command, and 4 accepted socket channels closed**.
7. Shutdown calls selector.wakeup(), waits for the event-loop thread to exit, and verifies that the selector is closed.

The demo protocol accepts **one short ASCII line per connection** and does not support sending multiple commands on the same socket. The 64-byte input buffer is bounded. A real service needs appropriate message limits, read timeouts, authentication, and resource protection.

### File SelectorCleanupDemo.java

~~~java
import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class SelectorCleanupDemo {
    static final class Server implements AutoCloseable {
        final CountDownLatch ready = new CountDownLatch(1);
        final CountDownLatch fourClosed = new CountDownLatch(4);

        final AtomicInteger accepted = new AtomicInteger();
        final AtomicInteger replies = new AtomicInteger();
        final AtomicInteger eof = new AtomicInteger();
        final AtomicInteger malformed = new AtomicInteger();
        final AtomicInteger closed = new AtomicInteger();

        volatile Selector selector;
        volatile int port;
        volatile boolean running = true;
        volatile Throwable failure;

        final Thread thread = new Thread(this::run, "selector-server");

        Server() {
            thread.start();
        }

        void closeKey(SelectionKey key) {
            key.cancel();
            if (key.channel() instanceof SocketChannel sc && sc.isOpen()) {
                try {
                    sc.close();
                } catch (IOException ex) {
                    failure = ex;
                } finally {
                    if (!sc.isOpen()) {
                        closed.incrementAndGet();
                        fourClosed.countDown();
                    }
                }
            }
        }

        void run() {
            try (Selector sel = Selector.open();
                    ServerSocketChannel listener =
                            ServerSocketChannel.open()) {
                selector = sel;
                listener.configureBlocking(false);
                listener.bind(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(), 0));
                port = ((InetSocketAddress)
                        listener.getLocalAddress()).getPort();
                listener.register(sel, SelectionKey.OP_ACCEPT);
                ready.countDown();

                try {
                    while (running) {
                        sel.select();
                        Iterator<SelectionKey> it =
                                sel.selectedKeys().iterator();

                        while (it.hasNext()) {
                            SelectionKey key = it.next();
                            it.remove();

                            if (!key.isValid()) {
                                continue;
                            }

                            try {
                                if (key.isAcceptable()) {
                                    SocketChannel peer =
                                            listener.accept();
                                    if (peer != null) {
                                        accepted.incrementAndGet();
                                        try {
                                            peer.configureBlocking(false);
                                            peer.register(
                                                    sel,
                                                    SelectionKey.OP_READ,
                                                    ByteBuffer.allocate(64)
                                            );
                                        } catch (IOException |
                                                RuntimeException ex) {
                                            try {
                                                peer.close();
                                            } finally {
                                                closed.incrementAndGet();
                                                fourClosed.countDown();
                                            }
                                            throw ex;
                                        }
                                    }
                                } else if (key.isReadable()) {
                                    onRead(key);
                                } else if (key.isWritable()) {
                                    onWrite(key);
                                }
                            } catch (IOException |
                                    RuntimeException ex) {
                                if (key.channel()
                                        instanceof SocketChannel) {
                                    malformed.incrementAndGet();
                                    closeKey(key);
                                } else {
                                    throw ex;
                                }
                            }
                        }
                    }
                } finally {
                    // Close accepted sockets that are still open on shutdown.
                    for (SelectionKey key :
                            new ArrayList<>(sel.keys())) {
                        if (key.channel() instanceof SocketChannel) {
                            closeKey(key);
                        }
                    }
                }
            } catch (Throwable ex) {
                failure = ex;
            } finally {
                ready.countDown();
            }
        }

        void onRead(SelectionKey key) throws IOException {
            SocketChannel peer =
                    (SocketChannel) key.channel();
            ByteBuffer input =
                    (ByteBuffer) key.attachment();

            int n = peer.read(input);
            if (n == -1) {
                eof.incrementAndGet();
                closeKey(key);
                return;
            }
            if (n == 0) {
                return;
            }

            // Demo only: a single LF-terminated ASCII command.
            for (int i = 0; i < input.position(); i++) {
                if (input.get(i) == (byte) '\n') {
                    byte[] line = new byte[i];
                    input.flip();
                    input.get(line);
                    String command = new String(
                            line, StandardCharsets.US_ASCII);

                    if (!"PING".equals(command)) {
                        throw new IOException(
                                "Unsupported command: " + command);
                    }

                    key.attach(ByteBuffer.wrap(
                            "PONG\n".getBytes(
                                    StandardCharsets.US_ASCII)));
                    key.interestOps(SelectionKey.OP_WRITE);
                    return;
                }
            }

            if (!input.hasRemaining()) {
                throw new IOException("Line too long");
            }
        }

        void onWrite(SelectionKey key) throws IOException {
            SocketChannel peer =
                    (SocketChannel) key.channel();
            ByteBuffer response =
                    (ByteBuffer) key.attachment();
            peer.write(response);

            // May be a partial write; keep OP_WRITE if bytes remain.
            if (!response.hasRemaining()) {
                replies.incrementAndGet();
                closeKey(key);
            }
        }

        @Override
        public void close() throws InterruptedException {
            running = false;
            Selector sel = selector;
            if (sel != null) {
                sel.wakeup();
            }
            thread.join(5000);
            if (thread.isAlive()) {
                throw new AssertionError(
                        "selector thread did not stop");
            }
        }
    }

    static Socket connected(int port) throws IOException {
        Socket client = new Socket();
        client.connect(new InetSocketAddress(
                InetAddress.getLoopbackAddress(), port), 3000);
        client.setSoTimeout(3000);
        return client;
    }

    static String command(int port, String text)
            throws IOException {
        try (Socket client = connected(port)) {
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            client.getOutputStream(),
                            StandardCharsets.US_ASCII));
            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(),
                            StandardCharsets.US_ASCII));

            out.write(text);
            out.write('\n');
            out.flush();
            return in.readLine();
        }
    }

    static void sendEof(int port) throws IOException {
        try (Socket client = connected(port)) {
            client.shutdownOutput();
            if (client.getInputStream().read() != -1) {
                throw new AssertionError(
                        "expected EOF after server close");
            }
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        Server server = new Server();
        try {
            check(server.ready.await(5, TimeUnit.SECONDS),
                    "not ready");
            check(server.failure == null,
                    "server startup failure");

            check("PONG".equals(command(server.port, "PING")),
                    "first PING");
            sendEof(server.port);
            check(command(server.port, "BAD") == null,
                    "BAD must close");
            check("PONG".equals(command(server.port, "PING")),
                    "second PING");

            check(server.fourClosed.await(5, TimeUnit.SECONDS),
                    "not all four client channels closed");
            check(server.accepted.get() == 4, "accepted count");
            check(server.replies.get() == 2, "reply count");
            check(server.eof.get() == 1, "EOF count");
            check(server.malformed.get() == 1, "error count");
            check(server.closed.get() == 4, "close count");
            check(server.failure == null,
                    "server loop failure");
        } finally {
            server.close();
        }

        check(!server.selector.isOpen(),
                "selector not closed");
        check(!server.thread.isAlive(),
                "selector thread still alive");

        System.out.println("PASS: 4 connections accepted");
        System.out.println("PASS: 1 EOF, 1 malformed command");
        System.out.println(
                "PASS: 2 PING responses after error isolation");
        System.out.println("PASS: 4 client channels closed");
        System.out.println("PASS: selector and loop stopped");
    }
}
~~~

### Compilation, Execution, and Output

Using JDK 17 or later, save with the exact filename **SelectorCleanupDemo.java**:

~~~bash
javac --release 17 -encoding UTF-8 SelectorCleanupDemo.java
java SelectorCleanupDemo
~~~

**Stdout on successful test** (logic verified on the Java runtime):

~~~text
PASS: 4 connections accepted
PASS: 1 EOF, 1 malformed command
PASS: 2 PING responses after error isolation
PASS: 4 client channels closed
PASS: selector and loop stopped
~~~

The third line counts **two PING responses in total**, one before and one **after** the BAD command. That PING after BAD proves the event loop was not terminated by a faulty request.

**Verification mechanism:** the program does not print the summary if assertions on accepted, replies, EOF, malformed, closed, or selector state fail. It uses **CountDownLatch** to wait for the server to be ready and for all four sockets to close, rather than relying on sleep to guess scheduling.

### 5.1. Successful PING Flow

~~~text
accept() -> non-blocking SocketChannel -> register(OP_READ, ByteBuffer)
OP_READ  -> read n>0 -> saw "PING\n" -> attach(PONG buffer)
         -> interestOps(OP_WRITE)
OP_WRITE -> channel.write(response buffer)
         -> if remaining > 0, wait for next OP_WRITE
         -> when fully sent: replies++, cancel key, close channel
~~~

SocketChannel.write(ByteBuffer) may consume only part of the bytes. Do not close immediately when write returns a positive number while bytes still remain. Only when the output buffer is empty should you close according to the **one command / one connection** protocol in the example. Closing the socket does not prove that the remote system has committed the business operation.

### 5.2. EOF Flow

~~~text
Client shutdownOutput()
      |
Server readiness OP_READ
      |
SocketChannel.read(input) = -1
      |
Demo has no pending response
      |
eof++, cancel key, close channel
~~~

The server does not send PONG for an EOF with no command. In another protocol, it might need to send a response **after EOF** before closing; that is why half-close must be distinguished from closing the entire connection.

### 5.3. Error-Inducing BAD Flow

~~~text
OP_READ -> receives "BAD\n"
        -> parser throws IOException
        -> catch only on the SocketChannel's SelectionKey
        -> malformed++, cancel key, close channel
        -> event loop continues accept/read/write
        -> next PING still receives PONG
~~~

This is per-connection **error isolation**. When the listener encounters a serious error, the program escalates to the server-failure branch instead of treating it as a bad command.

### 5.4. Shutting Down the Entire Server

Another thread sets **running=false** and calls **selector.wakeup()** so select returns from waiting. The event loop exits the while loop, runs finally to close any remaining client channels, and then try-with-resources closes the listener and selector. Afterwards, the test **joins** the event-loop thread and verifies that selector.isOpen() is false.

**selector.wakeup() does not replace selector.close().** It only prompts select to return control so the thread can complete shutdown itself. Likewise, **selector.close() does not replace closing accepted sockets**.

## 6. Cleaning Up Attachments, Buffers, and Potential Pitfalls

### Attachments Can Hold the Entire Connection State

In a service with a complex protocol, the attachment is typically an object holding the inbound ByteBuffer, an outbound ByteBuffer queue, half-close status, and timeouts.

~~~java
// Illustrates the state model; not a standalone runnable application.
final class ConnectionState {
    final ByteBuffer inbound = ByteBuffer.allocate(8192);
    final Deque<ByteBuffer> outbound = new ArrayDeque<>();
    boolean inputEnded;
    boolean closingAfterWrite;
}
~~~

When the socket ends, clear the queue, cancel any timeouts/scheduled tasks for the connection, close additional resources if any, and drop references so memory can be reclaimed. If there are outbound bytes to send after input EOF, you can set **closingAfterWrite=true**, remove OP_READ, and keep OP_WRITE until the queue is empty; only then cancel and close.

### Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| **Only calling key.cancel(), not closing SocketChannel** | Keeps socket/FD open even though key is invalid | Close the channel |
| **Only closing Selector, not closing accepted channels** | Accepted sockets may remain alive | Clean up each owned connection |
| **Forgetting iterator.remove()** | Reprocesses stale selected keys | Remove each key in the event loop |
| **Accessing readyOps/interestOps after cancel** | CancelledKeyException | Check isValid and do not reuse cancelled keys |
| **Treating read 0 as EOF** | Closes a live socket | Distinguish 0 from -1 |
| **Keeping OP_READ after EOF without changing state** | Can spin in an infinite ready-to-read loop | Switch to write-only if needed, or close |
| **Closing immediately on EOF despite pending response** | Drops the response in half-close protocols | Flush all outbound data before closing |
| **One client IOException exits the event loop** | A bad client kills the service | Catch per-key, distinguish listener failure |
| **Incrementing closed count before actually closing** | Inaccurate metrics | Count based on post-cleanup state |
| **Not closing socket if register fails after accept** | Leaks a socket with no handler | Accept loop cleans up on failed register |
| **Forgetting to bound input before LF/frame** | Malicious client exhausts RAM/CPU | Bound bytes and deadlines |
| **Always watching OP_WRITE even when queue is empty** | Event loop may spin CPU | Only watch OP_WRITE when output is pending |

### Executing Cleanup from a Single Owning Thread

An effective convention is to have only the **event-loop thread** modify interestOps, cancel keys, or close per-connection channels. Other threads submit stop requests via a concurrent queue and call **selector.wakeup()**:

~~~text
Worker/other thread:
    enqueue close request for connection X
    selector.wakeup()

Event loop:
    drain request from queue
    key.cancel()
    channel.close()
    clean up attachment/state
    continue select
~~~

This reduces races between reading selectedKeys and cancelling keys from another thread. If multiple threads concurrently modify a key and connection state, an explicit synchronization/ownership design is required; **ByteBuffer and application state are not inherently thread-safe**.

## 7. Testing All Required Branches

| Test Case | What to Assert |
| --- | --- |
| Valid PING | Server replies with PONG, channel closes per protocol |
| Client calls shutdownOutput immediately | read returns -1, not misinterpreted as read 0, channel closes |
| BAD/protocol exception | Only that client is closed; subsequent client still works |
| Client sends without LF and goes silent | Does not wait forever; size and time are bounded |
| Client sends oversized message | Protocol error, no unbounded allocation, connection closed |
| Write consumes only part of buffer | Remaining buffer is preserved, OP_WRITE continues |
| OP_WRITE with no outbound data left | OP_WRITE interest is disabled, no busy-spin |
| Cancel key then check isValid | isValid is false; do not blindly access readyOps |
| Shutdown while select is waiting | wakeup exits the event loop, listener/selector close |
| Shutdown while clients are still open | Server closes each accepted channel before terminating |
| Repeated start/stop cycles | No unbounded growth in FDs, threads, or active connections |

Measure on the JVM using **channel.isOpen()**, **selector.isOpen()**, accepted/closed counters, thread count, and heap; at the OS level, you can inspect file descriptors/handles and sockets across multiple cycles. **TIME_WAIT** after close can be a normal TCP state and does not by itself prove Java is leaking sockets; lingering **CLOSE_WAIT** is worth investigating when the application forgets to close after peer EOF.

## 8. Self-Check

**Question 1.** Does key.cancel() close the socket?  
**Answer:** No, you must close the SocketChannel when the connection ends.

**Question 2.** Does closing a SocketChannel affect its SelectionKey?  
**Answer:** Yes, the channel's registrations are cancelled, but state and additional resources still require cleanup.

**Question 3.** Does closing a Selector automatically close all accepted SocketChannels?  
**Answer:** No. The server is responsible for closing the channels it created/owns.

**Question 4.** Does a non-blocking read returning 0 mean the peer closed?  
**Answer:** No. 0 can mean no new bytes have arrived yet or the buffer has no space left. EOF is -1.

**Question 5.** Is it valid for a peer to call shutdownOutput and still wait for a response?  
**Answer:** Yes. TCP supports half-close. The server can send a response after EOF if the protocol requires it.

**Question 6.** Why is iterator.remove() necessary?  
**Answer:** selectedKeys does not automatically remove keys after the handler runs; removing avoids reprocessing stale readiness.

**Question 7.** If one client sends BAD, should the selector be closed?  
**Answer:** No. Close the failing connection and let other connections continue.

**Question 8.** Can you call interestOps(OP_WRITE) on a key that has already been cancelled?  
**Answer:** No. The key is invalid, and the operation may throw CancelledKeyException.

**Question 9.** How should EOF in the middle of a length-prefixed body be handled?  
**Answer:** Treat the incomplete frame as a protocol error; do not process a truncated payload as a complete message.

**Question 10.** If the server wants to shut down while select is waiting, what action wakes up select?  
**Answer:** Set the stop flag and call selector.wakeup(); the event loop then closes accepted channels, the listener, and the selector, and exits the thread.

## Conclusion

In Java NIO, **SelectionKey is a readiness registration, while SocketChannel is the connection resource**. **key.cancel() does not replace channel.close()**, and closing the selector does not automatically close every client socket. To handle this properly, you must recognize **read -1 as EOF**, **read 0 as not EOF**, respect half-close semantics, isolate errors per client, and have a consistent cleanup path for both failing connections and shutdown.

Only when tests show that **PING still works after BAD**, **EOF is handled**, **all SocketChannels are closed**, and **the selector thread terminates** do we have concrete evidence of proper key and resource lifecycles.

### References

- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): select, selectedKeys, wakeup, close.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): cancel, interestOps, readyOps, isValid, and attachment.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): read/write, EOF, half-close, close.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): accept and non-blocking registration.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): managing received and outbound bytes.
- [RFC 9293 — TCP](https://www.rfc-editor.org/rfc/rfc9293): TCP byte stream and connection-closing states.
