# Treating Readiness as a Signal to Re-verify with I/O Operations in Java NIO Selector

**Topic:** Java Advance - networking  
**Knowledge Group:** Selector

When using **java.nio.channels.Selector** with **SocketChannel** or **ServerSocketChannel** in **non-blocking** mode, the program does not dedicate a separate thread to each connection. Instead, a selector monitors the channels and operations the application is interested in, then wakes the loop when there is a **readiness** signal.

The key point: **readiness is a signal that you should attempt an I/O operation and inspect the actual result; it is not a guarantee that the operation will definitely transfer or receive data at the moment you execute it**. Between the time the OS detects the ready state and the time Java calls **accept()**, **finishConnect()**, **read()**, or **write()**, the state can change. Producer/consumer speed, buffer contents, the peer closing the connection, and concurrent operations also affect the outcome.

A proper NIO design always uses **the return value of the I/O call** as the basis for updating state, rather than inferring from **key.isReadable()**, **key.isWritable()**, or the number of keys returned by **select()**. This is the critical difference between a stable event loop and bugs such as lost bytes, lost messages, busy-loops, redundant reads, or closing at the wrong time.

## 1. Three State Layers: Interest, Readiness, and Actual I/O

For each registered channel, Java returns a **SelectionKey**. There are three independent concepts:

1. **Interest set**: which operations the application currently wants to be notified about, seen via **key.interestOps()**. For example, **OP_READ**, **OP_WRITE**, **OP_ACCEPT**, **OP_CONNECT**.
2. **Ready set**: which operations the selector observed as ready at **the selection step**, seen via **key.readyOps()** or **key.isReadable()**, **isWritable()**, **isAcceptable()**, **isConnectable()**.
3. **Actual I/O**: the answer from **channel.read(...)**, **channel.write(...)**, **server.accept()**, or **channel.finishConnect()** when the code actually calls them.

~~~text
Application registers: interestOps(OP_READ)
             │
             ▼
    Selector monitors channel
             │
             ▼
      select() / selectNow()
             │
             ▼
    selectedKeys(), readyOps()
             │  (signal observed at selection time)
             ▼
     Check key.isValid()
             │
             ▼
       Attempt read(buffer)
          /     |      \
        > 0     0       -1
       bytes   no       EOF: peer closed send side
       read   progress
             │
             ▼
   Update buffer, protocol state, interestOps
~~~

For instance, **key.isReadable() == true** means the channel was identified by the selector as having a read condition worth checking. It does **not** guarantee that **read()** will return a positive byte count or form a complete message:

- **read() > 0**: actually placed that many bytes into the **ByteBuffer**.
- **read() == 0**: no bytes were read this time; this can commonly happen with non-blocking I/O or when the destination buffer has no space left.
- **read() == -1**: the receiving side has reached **end-of-stream**; EOF/half-close must be handled according to the protocol, and must not be treated as "temporarily no bytes available".

Similarly, **key.isWritable()** does not prove that a **write(ByteBuffer)** will consume the entire buffer; it may write partially or **0** bytes. **isAcceptable()** does not replace checking whether **ServerSocketChannel.accept()** returns a real **SocketChannel** or **null**.

## 2. What Value Does Readiness Have If It Doesn't Guarantee Progress?

Readiness is still very useful: it helps the application **avoid blindly attempting I/O across thousands of channels**. The selector typically wakes up when there is a possibility that a registered operation can proceed without blocking. Thanks to that, a single event-loop thread can perform I/O for many connections.

However, treat readiness as a **hint to try**, not a business-level fact:

~~~text
Time T0: OS observes the channel is readable.
Time T1: selector returns a key with OP_READ.
Time T2: handler prepares to read; by now there may have been:
  - another thread operating on the same channel,
  - the sender closing the connection,
  - the application's destination buffer running out of space,
  - the channel state being cancelled/closed or changed.
Time T3: call channel.read(buffer).
At T3: only the return value / exception from read determines
        how many bytes were read, EOF, or an error.
~~~

You don't need a rare race condition to get this wrong: even over TCP loopback, **a single read() has no message boundaries**. Received data can be **partial**, **multiple messages stuck together**, or EOF. If a handler interprets **readable = a full request is available**, bugs can already occur even when all code runs on a single event-loop thread.

**Do not perform blocking I/O** after receiving an event just because a key reported ready. **SocketChannel/ServerSocketChannel** instances registered with a Selector must be in non-blocking mode; the handler itself must also preserve that mode and handle the "no progress" case.

## 3. Rules Table for the Four SelectionKey Operations

| Readiness flag | Typical valid channel | Operation to perform | Results to evaluate |
| --- | --- | --- | --- |
| **OP_ACCEPT** | **ServerSocketChannel** | **accept()** | Returns a new **SocketChannel** or **null** if no connection is immediately available to take |
| **OP_CONNECT** | **SocketChannel** performing non-blocking connect | **finishConnect()** | **true** if complete, **false** if not yet complete; or an exception if the connection failed |
| **OP_READ** | **SocketChannel** | **read(ByteBuffer)** | **> 0** bytes read; **0** no progress; **-1** EOF; or exception |
| **OP_WRITE** | **SocketChannel** | **write(ByteBuffer)** | Number of bytes actually taken from the source buffer; can be **0** or less than the bytes waiting to be sent |

The flags are a **bitmask**; a key can report multiple ready operations in a single select, and an event must update state/interest for the next round. Do **not** treat isReadable/isWritable as a permanently held state, and do not assume each ready event corresponds to one packet or one message.

**SelectionKey.isValid()** checks that the key has not been cancelled; a key can be **cancel()**led, a channel can be closed, or a selector can be closed during processing. In a concurrent environment, state can still change after checking isValid; you must close/clean up consistently when I/O throws an exception. **CancelledKeyException** can occur when accessing operations on an invalidated key.

**Flags are only valid per channel type.** Query **channel.validOps()** when you want to check which operations a channel type supports registering. Do not enable OP_ACCEPT on a regular SocketChannel, or OP_READ on a ServerSocketChannel.

## 4. The Correct Selector Loop: Select, Iterate, Remove Selected Key, Attempt I/O

Basic template (pseudocode, not a complete program):

~~~java
try (Selector selector = Selector.open()) {
    // Register non-blocking channels with appropriate interestOps.

    while (running) {
        int n = selector.select(1_000);  // Wait up to about 1 second for events.
        if (n == 0) {
            // Timeout, wakeup, or situation where no new keys were selected.
            // Still check shutdown/deadlines/pending work.
            continue;
        }

        Iterator<SelectionKey> iterator = selector.selectedKeys().iterator();
        while (iterator.hasNext()) {
            SelectionKey key = iterator.next();
            iterator.remove(); // Do not leave stale keys in the selected-key set.

            if (!key.isValid()) {
                continue;
            }

            // For each applicable readiness bit:
            // - call actual accept/finishConnect/read/write;
            // - check return value/exception;
            // - update buffer, protocol state, interestOps;
            // - cancel key/close channel on EOF or error.
        }
    }
}
~~~

The snippet above is an **explanatory skeleton**; it does not declare **running**, does not create channels, and cannot be used as a complete server. See the runnable program in section 9.

### Why Must You Call iterator.remove()?

**Selector.selectedKeys()** is the set of selected keys; keys **do not automatically disappear just because the handler finished reading/writing**. The loop typically calls **iterator.remove()** right after retrieving the key, before processing it. Otherwise, the program may reprocess stale keys in subsequent rounds, causing observed state and I/O operations to mismatch and increasing the risk of busy-loops or unintended repeated processing.

Do not call **selector.selectedKeys().clear()** indiscriminately while you still intend to iterate over and process keys. Using an iterator clarifies per-event ownership and makes per-key error handling straightforward.

### The Return Value of select() Is Not a Byte Count

- **select() / select(timeout)** returns information about keys whose readiness was updated, **not** the number of connections, bytes, or messages.
- **selectNow()** does not wait; it can return 0 when no new state is ready.
- **selector.wakeup()** can cause a waiting select call to return early. A **select() == 0** is not necessarily an error.
- **select(0)** in the Java Selector API means wait indefinitely (do not use it as a 0ms poll); to avoid waiting, use **selectNow()**.
- Selector timeouts do not automatically cancel connections; you need separate deadlines and state for connect, handshake, request, or idle timeouts.

You must **check actual progress** after select returns, even when a key indicates an operation is ready.

## 5. OP_ACCEPT: Ready to Accept Still Requires a Null Check

With a **ServerSocketChannel**:

~~~java
server.configureBlocking(false);
server.register(selector, SelectionKey.OP_ACCEPT);

// In the handler, when key.isAcceptable():
SocketChannel peer;
while ((peer = server.accept()) != null) {
    peer.configureBlocking(false);
    peer.register(selector, SelectionKey.OP_READ, new ConnectionState());
}
~~~

The above is a **snippet**; **server**, **selector**, and **ConnectionState** are variables/classes that the application must provide. **accept()** on a non-blocking ServerSocketChannel **can return null**, so do not dereference it or register a key if the result is null.

Why can it be null even though the key just had **isAcceptable() == true**?

- Readiness recorded the ability to accept a connection at selection time.
- Another handler may have already accepted the connection before this handler called accept.
- Network/channel state may have changed.
- A previous accept call in the same loop already drained all pending connections.

Using **while (accept() != null)** processes all connections currently available in the backlog until none can be retrieved immediately. Do **not** busy-loop calling accept when it returns null; return to the selector loop and wait for the next readiness event.

**After accept:** A newly accepted SocketChannel from a non-blocking ServerSocketChannel is typically also in non-blocking mode per the API, though calling **configureBlocking(false)** explicitly is good practice. Each connection must have its **own state**: inbound buffer, outbound buffer, parser/framer, deadline, and lifecycle. Do not treat a listener key as a key used to read/write connection data.

## 6. OP_CONNECT: Must Call finishConnect() and Check the Result

Non-blocking connect has two branches:

~~~java
// Snippet: remote is a validated InetSocketAddress; selector is already open.
SocketChannel channel = SocketChannel.open();
channel.configureBlocking(false);

boolean connectedNow = channel.connect(remote);
if (connectedNow) {
    channel.register(selector, SelectionKey.OP_READ);
} else {
    channel.register(selector, SelectionKey.OP_CONNECT);
}

// After key.isConnectable():
boolean connected = channel.finishConnect();
if (connected) {
    key.interestOps(SelectionKey.OP_READ);
    // Only add OP_WRITE if there is actually pending output.
} else {
    // Still pending; keep OP_CONNECT and retry when notified ready.
}
~~~

This is an **illustrative snippet**, not a complete program. You must handle **IOException** and close the channel if connect fails, and use an application deadline for connections that take too long. A non-blocking **connect(...)** call returning **false** does not mean the connection failed; it indicates the connection process has not completed yet.

**OP_CONNECT does not mean the connection has succeeded.** **finishConnect()** is what completes the process or throws an error such as **ConnectException**. Once connected, remove **OP_CONNECT** from the interest set; leaving an unnecessary flag enabled can easily cause the state machine to be invoked incorrectly on the next round.

Do not automatically enable **OP_WRITE** after connect just to "check readiness". For a connected TCP channel, OP_WRITE very easily reports ready whenever the send buffer has space, causing continuous wakeups even when there are no bytes to send.

## 7. OP_READ: Handle All Three Cases > 0, 0, -1

The handler must use **the actual read return value**, and the buffer must have remaining space:

~~~java
// Snippet: key belongs to a SocketChannel, inbound is in write mode.
int n = channel.read(inbound);

if (n > 0) {
    // Advance byte counter / parser progress.
    // Check whether a complete frame or characters are ready to process.
} else if (n == 0) {
    // No progress yet: keep buffer/state and wait for next readiness.
} else { // n == -1
    // Peer closed its send side; finalize frame or report truncated.
    // Close/cancel if the protocol does not support half-close.
}
~~~

**read() > 0** only means **n bytes** were read; it does not prove a text line, a JSON document, or a frame is complete. For example, a 4-byte length-prefixed protocol must keep accumulating until 4 header bytes are read, then continue reading the payload according to that length. If the buffer is full, the handler must **flip, parse, compact**, or apply backpressure before reading more; reading into a ByteBuffer with no remaining space can return **0** even if the key reported readable.

**read() == 0** on a non-blocking channel can come from no bytes being immediately available to read, state contention, or a full buffer. Do not turn n=0 into EOF; do not write a loop like **while (read(...) == 0) { }** because a thread can burn CPU uselessly. Keep appropriate interest ops and return to the selector; if the destination buffer is full, consume/free space or intentionally pause OP_READ instead of waiting for more data with nowhere to put it.

**read() == -1** is EOF on the receive side. If the protocol already has the complete request and allows half-close, the server may still need to send a response; if the request is missing bytes, handle it as a truncated frame. Do not treat EOF as "a new frame notification", nor call read infinitely.

### Readiness Can Fire When the Peer Closes

When the peer sends a FIN or an error condition occurs, the selector can still mark the channel readable. At that point **read()** returns **-1** or throws **IOException**; readiness does not mean "the peer is still sending useful data".

### What If One Event Has More Bytes Available?

With non-blocking reads, you can read multiple times within **a single handler turn** as long as the buffer has space and there is a **work limit** so other connections are not starved. A read loop can continue while **n > 0**, stop when **n == 0**, and handle EOF when **n == -1**. Do not assume "one successful read equals a complete message". In the demo below, the request is fixed at 4 bytes to focus on readiness; each read continues on readiness until 4 bytes are received.

## 8. OP_WRITE: Writable Signal Does Not Guarantee Sending Everything

In non-blocking mode, **SocketChannel.write(ByteBuffer)** reads some number of bytes from **position** to **limit** of the source buffer. The result can be **0** or a positive number smaller than the initial **remaining()**.

~~~java
// Snippet: pending is in read mode, with bytes left to send.
int n = channel.write(pending);

if (pending.hasRemaining()) {
    // Not fully sent: keep this same ByteBuffer and OP_WRITE.
    // Do not clear() or compact() arbitrarily without managing the remainder.
} else {
    // All bytes in the buffer have been handed off to the channel on the Java side.
    // Remove OP_WRITE if there is currently no more pending output.
    key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
}
~~~

This is only a **snippet** and does not guarantee the peer has received or processed the bytes; a successful write usually only reflects that the bytes were accepted by the socket layer for transport.

**Rules for handling partial writes:**

1. Put the **ByteBuffer** in read mode using **flip()** after encoding/filling data.
2. Call **write()** when given the opportunity to write, then check **pending.hasRemaining()**.
3. If bytes remain, **preserve position/limit and unsent data** for the next OP_WRITE turn. If **n == 0**, avoid spinning by returning to the selector.
4. If no bytes remain, **remove OP_WRITE** when the outbound queue has no more data. If there are multiple buffers, only advance to the next buffer after the current one is properly drained.
5. If a producer generates new output from another thread, update the queue/state safely and wake up the selector when needed (see section 11).

**Do not register OP_WRITE permanently for all clients.** A TCP channel is usually writable whenever its send buffer has room, causing the selector to fire continuously while the handler has no bytes to send. This is a very common CPU-burning event-loop bug. Only express interest in OP_WRITE when there is actually data waiting or another specific reason.

**Application buffer differs from kernel send buffer:** **pending.hasRemaining() == false** means the channel has consumed those bytes from Java's ByteBuffer, not that the peer has sent an application acknowledgment. To confirm a transaction, you must have a protocol-level response/ACK.

## 9. Complete Java 17+ Program: Single Selector, TCP Loopback, Read/Write with Progress Checks

The runnable example below uses one non-blocking **ServerSocketChannel** registered with **OP_ACCEPT**, and a blocking client solely to generate the PING/PONG traffic within the same program. The selector loop:

- Removes each key from **selectedKeys** via **iterator.remove()**.
- Checks **key.isValid()** before processing.
- On **isAcceptable()**, calls **accept()** until it returns **null**, registering **OP_READ** for the connection.
- On **isReadable()**, calls **read(ByteBuffer)** and distinguishes **-1**, **0**, and **> 0**; only transitions to sending a response once all 4 bytes are received.
- On **isWritable()**, calls **write(ByteBuffer)** and only finishes when the buffer has no remaining bytes.
- Includes deadlines and timeouts for the client to prevent hanging indefinitely in the demo.
- Output does not depend on a random port or forcing a zero-byte read: **0** or **partial write** results are proper defensive code branches, though they are not guaranteed to occur on a single loopback run.

Create the file **ReadinessRecheckDemo.java**:

~~~java
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
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

public class ReadinessRecheckDemo {
    private static final class State {
        final ByteBuffer request = ByteBuffer.allocate(4);
        ByteBuffer response;
    }

    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.configureBlocking(false);
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            listener.register(selector, SelectionKey.OP_ACCEPT);
            InetSocketAddress endpoint =
                    (InetSocketAddress) listener.getLocalAddress();

            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> client = executor.submit(() -> {
                    try (Socket socket = new Socket()) {
                        socket.connect(endpoint, 3_000);
                        socket.setSoTimeout(3_000);
                        socket.getOutputStream().write(
                                "PING".getBytes(StandardCharsets.US_ASCII));
                        byte[] response = new byte[4];
                        new DataInputStream(socket.getInputStream())
                                .readFully(response);
                        return new String(response, StandardCharsets.US_ASCII);
                    }
                });

                boolean completed = false;
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (!completed && System.nanoTime() < deadline) {
                    if (selector.select(500) == 0) {
                        continue;
                    }

                    Iterator<SelectionKey> iterator =
                            selector.selectedKeys().iterator();

                    while (iterator.hasNext()) {
                        SelectionKey key = iterator.next();
                        iterator.remove();

                        if (!key.isValid()) {
                            continue;
                        }

                        if (key.isAcceptable()) {
                            ServerSocketChannel server =
                                    (ServerSocketChannel) key.channel();
                            SocketChannel peer;
                            while ((peer = server.accept()) != null) {
                                peer.configureBlocking(false);
                                peer.register(selector,
                                        SelectionKey.OP_READ, new State());
                            }
                            continue;
                        }

                        SocketChannel peer = (SocketChannel) key.channel();
                        State state = (State) key.attachment();

                        if (key.isReadable()) {
                            int n = peer.read(state.request);
                            if (n == -1) {
                                key.cancel();
                                peer.close();
                                throw new EOFException(
                                        "Peer closed before request finished");
                            }
                            if (n > 0 && !state.request.hasRemaining()) {
                                state.request.flip();
                                byte[] request = new byte[4];
                                state.request.get(request);
                                String value = new String(
                                        request, StandardCharsets.US_ASCII);
                                System.out.println("serverReceived=" + value);

                                state.response = ByteBuffer.wrap(
                                        "PONG".getBytes(StandardCharsets.US_ASCII));
                                key.interestOps(SelectionKey.OP_WRITE);
                            }
                            // n == 0: no progress yet; keep buffer and wait.
                        }

                        if (key.isValid() && key.isWritable()
                                && state.response != null) {
                            int n = peer.write(state.response);
                            if (!state.response.hasRemaining()) {
                                key.cancel();
                                peer.close();
                                completed = true;
                            }
                            // If n == 0 or partial write, keep OP_WRITE.
                        }
                    }
                }

                if (!completed) {
                    throw new IOException("Selector demo timed out");
                }
                System.out.println("clientReceived=" +
                        client.get(3, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with **Java 17 or later** (no internet required):

~~~bash
javac --release 17 -encoding UTF-8 ReadinessRecheckDemo.java
java ReadinessRecheckDemo
~~~

**Exact stdout of a successful run**, tested on JDK 24 with **javac --release 17**:

~~~text
serverReceived=PING
clientReceived=PONG
~~~

### Why Does This Example Demonstrate the Principle Properly?

1. The listener calls **configureBlocking(false)** before **register(selector, OP_ACCEPT)**. The OS assigns port 0 on loopback, and the client uses the actual bound endpoint.
2. **isAcceptable()** only triggers an **accept()** attempt; the while loop does not assume it will always receive a connection and stops when **accept() == null**.
3. Each connection has a **State** attached to its **SelectionKey**. **ByteBuffer request** has space for 4 bytes; the handler only transitions to the response when all **4 bytes** are read, not simply because OP_READ reported ready.
4. **read() == -1** before the full request is received is treated as a truncated request and throws **EOFException**. **read() == 0** does not alter state and does not close the connection.
5. Once the full request is received, the handler **flip()**s the buffer, prints **PING**, prepares the response, and switches interest to **OP_WRITE**. This avoids writing before output exists.
6. For OP_WRITE, the handler uses **write()** and **hasRemaining()**. An incomplete write keeps the remaining bytes and interest for the next turn; it only closes after all 4 response bytes have been accepted by the channel.
7. The client's **DataInputStream.readFully(byte[4])** reads all 4 bytes of **PONG**, avoiding the assumption that a single read gets everything.
8. The demo operates on 1 connection to focus on the principle; in a real server you need to replace **completed** with a long-lived event loop and add resource limits, per-key exception handling, per-connection framing, close policy, and managed shutdown.

**Do not over-infer:** In a single loopback run, you may not observe read returning 0 or a partial write because 4 bytes is very small. **Correctness lies in the code being prepared to handle those valid outcomes**, not in forcing them to happen. To test rare branches, use a fake channel/test adapter, constrained send buffers, network simulation, or controlled tests; never claim an event only happens because you added a sleep.

## 10. Why Readiness Must Not Be Used as a Business Condition

### Wrong: Treating readable as having a full request

~~~java
// Anti-pattern: ignores return value and framing.
if (key.isReadable()) {
    channel.read(buffer);
    handleRequest(buffer); // Request may be incomplete, or read returned 0/-1.
}
~~~

Not only does this miss handling **read() == 0/-1**; it also fails to manage **flip()/compact()** and does not determine request boundaries. It can parse garbage bytes, lose leftover bytes, or reply when a message is incomplete.

**The right principle** is: read, check **n**, update the accumulator, extract complete frames, keep the remainder, and then decide what output to enqueue. With length-prefixed or delimited protocols, the parser must tolerate arbitrary fragmentation.

### Wrong: Treating writable as clearing the entire outbound queue

~~~java
// Anti-pattern: write can send 0 or partial bytes.
if (key.isWritable()) {
    channel.write(outgoing);
    outgoing.clear();  // Loses bytes if outgoing.hasRemaining()!
}
~~~

**Right:** preserve the buffer until **hasRemaining() == false**. Only clear it for reuse after all bytes have been sent or transferred in a controlled manner. If output is a queue of multiple buffers, the sending logic must preserve the offset of the remaining data.

### Wrong: Retrying read/write in a tight loop when returning 0

~~~java
// Anti-pattern: can spin the CPU at 100%.
while (channel.read(buffer) == 0) {
    // No progress and not waiting for new readiness.
}
~~~

The right approach is to return to the selector or schedule conditionally on the event loop; if the buffer is full, handle capacity/backpressure first. A readiness callback does not grant permission to spin indefinitely until enough bytes arrive.

### Wrong: Keeping OP_WRITE enabled even when there is no data

~~~java
// Anti-pattern if there is no actual output.
key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
~~~

When there is no pending write, OP_WRITE is usually continuously ready. Instead, use:

~~~java
int ops = SelectionKey.OP_READ;
if (hasPendingOutput) {
    ops |= SelectionKey.OP_WRITE;
}
key.interestOps(ops);
~~~

Both snippets above require application-defined **key** and **hasPendingOutput** variables. **OP_READ** should also be paused when the inbound queue hits its limit and the consumer cannot keep up; there must be a path to re-enable it after capacity is freed.

### Wrong: Believing one ready event corresponds to one message

~~~text
TCP sender writes:   [frame A] [frame B]
SocketChannel.read:  [half of A] [rest of A and all of B]

Or:
TCP sender writes:   [frame A]
SocketChannel.read:  [all of A]
~~~

Selector does not provide framing. A single read can receive less than, exactly, or more than one frame's worth of data. The parser must track length, delimiters, decode state, and leftover bytes across multiple events.

## 11. Key Lifecycle, Cancellation, and Concurrency

**selectedKeys** is not an immutable queue; during processing:

- **key.cancel()** marks the key to be removed from the selector through the cancellation process; **key.isValid()** will no longer be true.
- **channel.close()** causes the corresponding key to become invalid/cancelled; any subsequent read/write may throw an exception.
- **IOException**, **ClosedChannelException**, and **CancelledKeyException** must be handled according to connection ownership: close the channel, cancel the key, release buffers/timers, update state, and avoid crashing the entire server because of one faulty client.
- A key may have multiple readiness bits set or an attachment whose state has changed; use the actual connection state in the handler rather than inferring solely from the ready set.

### Updating interestOps from Another Thread

In real systems, a worker thread may produce a response for a connection while the selector thread is blocked in select. A common design is:

1. The worker **enqueues** the response into the connection's **thread-safe** outbound queue.
2. The worker enqueues an **interestOps update command** to the event-loop thread's task queue.
3. The worker calls **selector.wakeup()** so the selector processes the task promptly.
4. The event-loop thread drains the task, verifies the key is still valid, enables **OP_WRITE**, and then writes upon readiness.

~~~text
Worker thread
  ├─ puts response into synchronized queue
  ├─ puts "enable OP_WRITE" task into selector task queue
  └─ selector.wakeup()
                 │
                 ▼
Selector thread: select() returns → process tasks → resume select
                 └─ isWritable → attempt write() → check remaining bytes
~~~

Multiple threads should not concurrently read/write the same **SocketChannel** and mutate the **position/limit** of a ByteBuffer without synchronization rules. Some channel methods can be called from other threads per the API, but correctness of the **state machine** remains the application's responsibility.

**wakeup() does not make a channel writable**. It only unblocks the selector so it can process pending work; subsequent I/O must still rely on **read/write results**. When coordinating interestOps from another thread is required, clearly define who owns the key and avoid races between close, cancel, enqueue, and enabling OP_WRITE.

### Selector Readiness and Fairness

A connection sending a large amount of data can keep the handler busy for a long time if the application keeps reading/writing until exhausted. Even when every read makes progress, an event loop can starve other connections. Set a **work budget** by byte count or time slice per handler turn, then return to the selector to distribute work. This is a **fairness** concern and does not contradict readiness being a useful signal.

## 12. Deadlines, EOF, and Backpressure Cannot Be Inferred from Selector

Latency has multiple layers that must be managed separately:

| Issue | Cannot be inferred from readiness | How to handle |
| --- | --- | --- |
| Connect takes too long | **OP_CONNECT** does not set a connect timeout | Deadline for CONNECTING state; close on expiration |
| Request missing bytes | **OP_READ** does not mean full message | Parser/frame accumulator + timeout/size limit |
| No new bytes | **select() == 0** does not mean the peer is dead | Protocol-level idle timer/heartbeat |
| Sender is congested | **OP_WRITE** does not mean the queue will drain | Partial-write state and backpressure |
| Peer closed send side | Ready bits do not cleanly distinguish FIN from data | **read() == -1** and protocol half-close |
| Program is shutting down | **isBound() / key.readyOps()** does not mean service is ready | Separate lifecycle state, controlled cancel/close |

### Practical Backpressure

If a peer reads slowly, writing to a non-blocking SocketChannel can return 0. Java's outbound queue will keep growing if the handler continues accepting messages and generating responses. You must **cap total pending bytes** per connection, optionally pausing OP_READ or reporting an error/overload when policy limits are exceeded. Growing buffers without bound merely shifts the problem to RAM/GC.

Conversely, when the parser/consumer cannot keep up with inbound data, do not keep reading indefinitely just because the key is readable. Pause **OP_READ** interest when a high watermark is exceeded and re-enable it when the queue drops to a safe level. Every interest change must reflect real state, avoiding lost wakeups or leaving no operations registered.

### EOF and Half-Close

With TCP, a peer can call **shutdownOutput()**, causing the receiver to see EOF while still remaining capable of receiving a response in the opposite direction. A server aware of protocol half-close can transition its state to **SEND_RESPONSE** instead of immediately closing the whole socket. The demo in section 9 intentionally treats EOF before receiving the full 4-byte request as an error, and once the full request is received, no further reads are needed.

## 13. Scenarios to Test to Prove Event Loop Correctness

Rather than testing only the happy path, simulate valid I/O outcomes:

| Operation | Test scenario | Expected behavior |
| --- | --- | --- |
| **accept()** | Occasionally returns **null** | Handler stops trying and returns to select, does not create a key from null |
| **finishConnect()** | Returns false while pending or throws IOException | Preserves/transitions state validly; cleans up on timeout/failure |
| **read() > 0** | Header/payload split across multiple reads | Frame accumulator preserves data accurately |
| **read() == 0** | Non-blocking has no bytes yet or dst has no remaining | Does not close connection, does not spin |
| **read() == -1** | EOF before frame completes | Detects truncated frame, does not parse as complete message |
| **write() < remaining** | Transfers only part of ByteBuffer | Preserves position and pending bytes, OP_WRITE continues |
| **write() == 0** | Send buffer temporarily full | Does not clear, does not busy-loop |
| **OP_WRITE always ready** | Queue is empty yet OP_WRITE remains enabled | Must disable OP_WRITE once pending is drained |
| **key cancelled** | Close while events are pending | Skips invalid key, cleans up without double-close logic |
| **selector.select() returns 0** | Timeout or wakeup | Continues event loop and processes tasks/deadlines |

**Some tests should use fake channels/adapters** or a test harness to force specific outcomes. Do not rely on sleep or artificially slowing the network and claiming you can reliably reproduce read()==0 after OP_READ across all OSes/JDKs.

### Practice Exercises

1. Change the demo from a fixed 4-byte protocol to a 4-byte **length-prefix** (big endian) and UTF-8 body. Send the body in multiple chunks; prove the parser only processes once all bytes arrive, without relying on a single isReadable.
2. Add an outbound **ByteBuffer** larger than the send buffer. Print the number of **write** calls and total bytes, ensuring the buffer is only released when **!hasRemaining()** and the client reads everything. Experiment with client read delays without relying on a fixed number of writes.
3. Write a non-blocking SocketChannel client using **OP_CONNECT**. Test connecting to an open port and an unlistened port; handle **finishConnect()** returning true, false, or throwing an exception.
4. Add deadlines for incomplete requests, idle timeouts, and graceful shutdown; verify that select() returning 0 does not mistakenly close a valid connection.
5. Have a worker thread build the response after the handler reads. Design a task queue + **selector.wakeup()** and ensure only the event-loop thread updates interestOps.
6. Set watermarks on the outbound queue; pause OP_READ when the queue grows too large, and re-enable it once drained. Explain why simply keeping OP_WRITE enabled continuously is not enough to protect RAM.

## 14. Common Mistakes from Misunderstanding Readiness

| Misconception | Consequence | Fix |
| --- | --- | --- |
| "OP_READ means a full request is ready." | Incomplete/corrupted frame parsing | Check **n** from read, accumulate and parse by framing |
| "OP_WRITE means the whole buffer can be written." | Lost bytes on partial write | Check **hasRemaining()** and keep ByteBuffer |
| "Accept ready means accept cannot be null." | NullPointerException or broken handler | Check result, loop until null |
| "OP_CONNECT means connected." | Using channel before connection completes | Call **finishConnect()** and check return/exception |
| "read() == 0 is equivalent to EOF." | Closing valid connections | Only **-1** is EOF on SocketChannel |
| "select() == 0 means the server is dead." | Stopping the event loop incorrectly | Account for timeout, wakeup, separate task/lifecycle |
| "Handling a key removes it from selectedKeys." | Reprocessing stale keys, unstable event loop | **iterator.remove()** for every key |
| "Keeping OP_WRITE enabled forever is fine." | Busy-loop and high CPU | Enable only when bytes need to be sent |
| "A key valid at first stays valid forever." | CancelledKeyException/closed channel | Check state and clean up per event |
| "Adding more threads will fix lost bytes." | Worse races, state bugs remain | Fix state machine, buffers, and I/O return checks |
| "One read returns an entire TCP packet." | Broken framing, merged/split messages | TCP is a byte stream, no message boundaries |
| "Successful write means the peer processed it." | False business ACK | Use application response and deadlines |

## 15. Safe Selector Implementation Checklist

- [ ] Is the channel **configureBlocking(false)** before registering?
- [ ] Does interestOps match the **current state** of each connection and **validOps()**?
- [ ] Is **select() == 0** handled properly without treating it as an I/O failure?
- [ ] Is every key **iterator.remove()**d from the selected set and checked with **isValid()**?
- [ ] Does each ready flag lead to an **actual I/O operation** or a justified state decision?
- [ ] Is **accept() == null** handled gracefully as normal?
- [ ] Is **finishConnect()** called, checking true/false/IOException, with a connect deadline?
- [ ] Does **read()** handle >0, 0, -1 separately and ensure buffer capacity remains?
- [ ] Does **write()** preserve unconsumed bytes on partial/0 writes without clearing too early?
- [ ] Is **OP_WRITE** removed when output is drained, and re-enabled when new output arrives?
- [ ] Is message framing/parsing independent of readiness?
- [ ] Are there queue limits, per-key workload limits, backpressure, and timeouts?
- [ ] Do key cancel, channel close, EOF, and exceptions have consistent cleanup?
- [ ] If other threads enqueue work, is there synchronization and **selector.wakeup()** when appropriate?
- [ ] Do tests cover zero-progress, partial I/O, and peer disconnect cases?

**Final takeaway:** Selector tells you **which channels are worth trying I/O on**, not **the outcome of the I/O**. Treat **isAcceptable/isConnectable/isReadable/isWritable** as a **signal**; then call **accept/finishConnect/read/write** and handle **null, false, 0, -1, partial results, or exceptions** according to a clear state machine. That separation is what makes an NIO program resilient to TCP fragmentation, state contention, and real-world load.

**Official API references:** [Selector (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html), [SelectionKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html), [SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html), [ServerSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html), and [ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html).