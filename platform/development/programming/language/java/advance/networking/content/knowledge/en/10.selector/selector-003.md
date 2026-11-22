# Interest Set, Ready Set, and OP_ACCEPT, OP_CONNECT, OP_READ, OP_WRITE Flags in Java NIO Selector

## Lesson Objectives

`java.nio.channels.Selector` is a core component of Java NIO that allows a single thread to monitor **multiple selectable channels**, instead of creating a blocking thread per socket. In real-world network programming, the most confusing part is not the `select()` call itself, but the two operation sets of `SelectionKey`:

- **Interest set:** the operations **the application wants to be notified about** for availability in subsequent selection cycles.
- **Ready set:** the operations that **the selector has recorded as ready** during the most recent selection operation.

The `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, and `OP_WRITE` flags are **bit masks**, not four mutually exclusive states. A key can be interested in multiple operations, and readiness only indicates that **I/O can be attempted**—it does not guarantee that the entire operation will succeed or process all data immediately.

After this lesson, you will be able to accurately explain, use, and debug `interestOps()`, `readyOps()`, `validOps()`, and the four flags above; build a `select() → selectedKeys() → process → remove()` event loop; manage `OP_WRITE` to avoid CPU spin; and transition `OP_CONNECT` to `OP_READ/OP_WRITE` after `finishConnect()`.

The examples use **Java 17+** and TCP loopback. Points related to `DatagramChannel` are noted in the comparison section; do not confuse TCP server `OP_ACCEPT` with receiving UDP datagrams.

## 1. The Right Mental Model for Selector and SelectionKey

In the Java NIO model:

```text
                      Selector
              ┌─────────────────────┐
              │ registered keys     │
              │ selected keys       │
              └──────────▲──────────┘
                         │ select()
             ready state │
                         │
       ┌─────────────────┴─────────────────┐
       │                                   │
ServerSocketChannel                  SocketChannel #1
interest: OP_ACCEPT                  interest: OP_READ
ready:    OP_ACCEPT (when peer)      ready:    OP_READ (when data/EOF)

                                         SocketChannel #2
                                         interest: OP_CONNECT
                                         ready:    OP_CONNECT (connect done/error)

                                         SocketChannel #3
                                         interest: OP_READ | OP_WRITE
                                         ready:    OP_WRITE (frequently!)
```

A `SelectableChannel` registered with a `Selector` creates a `SelectionKey` representing the **registration between that specific channel and that specific selector**. A channel can be registered with different selectors, but with **a specific selector** there is only one key for that channel. Calling `register(selector, ops, attachment)` when the channel is already registered and the key is still valid updates the interest operations/attachment of that registration rather than creating a second key for the same pair.

Three different sets/concepts must be distinguished:

| Concept | API | Contents | Who modifies it |
|---|---|---|---|
| Registered-key set | `selector.keys()` | Keys currently registered with the selector, unless cancelled/cleaned up | Register, cancel/close, and the key cleanup process |
| Selected-key set | `selector.selectedKeys()` | Keys for which the selector detected readiness and that have not yet been removed from the selected set by the application | Selector adds/updates; **application must remove/clear after processing** |
| Interest set of a key | `key.interestOps()` | Bit mask of operations the application wants to monitor | Application via `interestOps(...)`/corresponding methods |
| Ready set of a key | `key.readyOps()` | Bit mask of readiness recorded by the selector | Selector during select processing, not `interestOps(...)` |

**Example:** a connected `SocketChannel` has `interestOps() == OP_READ` but `readyOps() == 0` until the selector observes readable data, EOF, or a related state. Conversely, once a key is already in the selected set, changing the interest set **does not automatically clear the old ready set**.

**Key point:** `readyOps()` is a **selection state snapshot**, not a queue of immutable events like “add one event for every 1 byte”. If you do not drain the data or do not remove the key from the selected-key set, subsequent processing can easily fail or repeat the stale state.

### Selector Does Not Turn I/O into Fully Asynchronous I/O

A standard event loop uses **non-blocking** channels. `select()` may block to **wait for readiness**, whereas I/O operations such as `read()` or `write()` on a non-blocking channel must handle transient results (`0`, partial read/write) themselves. Selector does not automatically allocate unbounded buffers, parse protocols, manage request deadlines, or decide when to close a connection.

## 2. The Four Operation Constants: Bit Values and Valid Channels

In `java.nio.channels.SelectionKey`, four constants are defined with the following values:

| Constant | Numeric Value | Bit Mask (illustrative) | Readiness Meaning |
|---|---:|---|---|
| `OP_READ` | `1` | `0001` | Reading can be attempted; could also be EOF/close/error |
| `OP_WRITE` | `4` | `0100` | Writing to the transport-layer buffer can be attempted |
| `OP_CONNECT` | `8` | `1000` | Non-blocking connect can complete or report an error on finish |
| `OP_ACCEPT` | `16` | `1 0000` | Listening TCP channel has a connection waiting to be accepted |

**Do not guess bit order from name order**: `OP_WRITE` is 4, `OP_CONNECT` is 8, and `OP_ACCEPT` is 16. Always use the constants directly instead of hard-coding numbers.

### 2.1. Which Channel Types Accept Which Flags?

| Channel | Registrable Operations | Usage Example |
|---|---|---|
| `ServerSocketChannel` | **`OP_ACCEPT`** | Waiting for a new TCP client |
| `SocketChannel` | **`OP_CONNECT \| OP_READ \| OP_WRITE`** | Opening a non-blocking TCP connection, reading, and writing |
| `DatagramChannel` | **`OP_READ \| OP_WRITE`** | Receiving/sending UDP datagrams |
| `Pipe.SourceChannel` | **`OP_READ`** | Reading from a pipe |
| `Pipe.SinkChannel` | **`OP_WRITE`** | Writing to a pipe |

`ServerSocketChannel` does **not** use `OP_READ` to receive request bytes; it only accepts connections via `accept()`. After accepting, you register **the returned `SocketChannel`** with `OP_READ` or `OP_WRITE`.

UDP has no TCP handshake or `accept()`. With `DatagramChannel`, `OP_READ` indicates a datagram can be received; do not register `OP_ACCEPT` or `OP_CONNECT` for UDP. If a program calls `register(selector, SelectionKey.OP_ACCEPT)` on a `SocketChannel`, the bit set is not in `validOps()` and Java may throw `IllegalArgumentException`.

### 2.2. Combining Flags with Bitwise OR

```java
// Illustrative snippet, assuming key is valid and the channel supports the flags.
key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
```

`|` is bitwise OR. The result `1 | 4 == 5` means monitoring **both reading and writing**; it is not adding two business states or “switching from read to write”.

Checking bits:

```java
int interests = key.interestOps();
boolean wantsRead = (interests & SelectionKey.OP_READ) != 0;
boolean wantsWrite = (interests & SelectionKey.OP_WRITE) != 0;
```

With `&`, only shared bits are preserved. Do not write `interests == OP_READ` to ask “is read interested?”, because if the interest mask is `OP_READ | OP_WRITE`, equality comparison with `OP_READ` returns `false`, even though the read bit is set.

### 2.3. `validOps()` Is the Channel's Capability Contract

`SelectableChannel.validOps()` returns the bit set that the channel allows. Before dynamically building a register/interest mask, you can check:

```java
// Illustrative snippet: channel is a SelectableChannel.
int requested = SelectionKey.OP_READ;
if ((requested & ~channel.validOps()) != 0) {
    throw new IllegalArgumentException("Unsupported operation for channel");
}
```

This code is only an illustrative snippet without a standalone `channel` variable. It is useful when an application handles multiple channel types in a single event loop; do not confuse valid flags with actual readiness that has occurred.

## 3. Java 17+: Checking Bits and `validOps()` with a Runnable Program

Create the file **`SelectorOpsMatrix.java`**:

```java
import java.nio.channels.DatagramChannel;
import java.nio.channels.SelectionKey;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;

public class SelectorOpsMatrix {
    public static void main(String[] args) throws Exception {
        System.out.println("OP_READ=" + SelectionKey.OP_READ);
        System.out.println("OP_WRITE=" + SelectionKey.OP_WRITE);
        System.out.println("OP_CONNECT=" + SelectionKey.OP_CONNECT);
        System.out.println("OP_ACCEPT=" + SelectionKey.OP_ACCEPT);
        try (ServerSocketChannel server = ServerSocketChannel.open();
             SocketChannel tcp = SocketChannel.open();
             DatagramChannel udp = DatagramChannel.open()) {
            System.out.println("Server accepts: "
                    + ((server.validOps() & SelectionKey.OP_ACCEPT) != 0));
            System.out.println("TCP supports connect: "
                    + ((tcp.validOps() & SelectionKey.OP_CONNECT) != 0));
            System.out.println("UDP supports accept: "
                    + ((udp.validOps() & SelectionKey.OP_ACCEPT) != 0));
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac --release 17 -encoding UTF-8 SelectorOpsMatrix.java
java SelectorOpsMatrix
```

**Compiled and verified stdout:**

```text
OP_READ=1
OP_WRITE=4
OP_CONNECT=8
OP_ACCEPT=16
Server accepts: true
TCP supports connect: true
UDP supports accept: false
```

These are not values measured randomly from a network interface: the four bit values belong to the `SelectionKey` contract; `validOps()` reflects the opened channel type, without needing a remote server. The program does not call `register` or `select`; it only verifies **bit mask operations and the valid flag range**.

## 4. Interest Set: What Does the Program Want to Be Notified About?

The **interest set** answers the question: “In the next select cycle, which kinds of readiness do I want to monitor on this channel?”

Access:

```java
int current = key.interestOps();   // Read the current bit mask.
key.interestOps(SelectionKey.OP_READ); // Replace the entire interest mask.
key.interestOps(0);                // Temporarily interested in no operations.
```

This is an **illustrative snippet** assuming a valid key. `interestOps(0)` **does not close the socket and does not cancel the key**; it only stops registering interest in I/O operations until re-enabled.

Common cases:

- `ServerSocketChannel` just bound/listening: register `OP_ACCEPT`.
- `SocketChannel` connecting in non-blocking mode: register `OP_CONNECT` if `connect(...)` returns `false`.
- Connected TCP socket waiting for requests: register `OP_READ`.
- Outbound data **waiting to be written**: add or switch to `OP_WRITE` until the buffer is flushed.
- Nothing left to send: **turn off `OP_WRITE`** to avoid waking up the CPU continuously because the socket usually has space available for writing.

### 4.1. Changing the Interest Set Is an Application Decision, Not New Readiness

Suppose a socket is already ready for read; you call:

```java
key.interestOps(SelectionKey.OP_WRITE);
```

This call **does not instantaneously turn `readyOps()` into `OP_WRITE`**. The ready set is only updated by select operations; the previously detected read bit may still remain in the old snapshot. You must distinguish **future selection intent** from **observed state**.

Since Java 11, `interestOpsOr(int)` and `interestOpsAnd(int)` exist to modify bits **atomically** without manually doing read–modify–write on the mask. With Java 17:

```java
// Illustrative: add OP_WRITE while keeping other bits intact.
key.interestOpsOr(SelectionKey.OP_WRITE);

// Illustrative: remove only OP_WRITE without clearing OP_READ.
key.interestOpsAnd(~SelectionKey.OP_WRITE);
```

These methods still require the key to be valid and only use bits supported by the channel. Note that `~OP_WRITE` is bitwise NOT, commonly combined with AND to clear the exact write bit. Atomic updates help prevent lost bits when two threads modify `interestOps()` via a read-modify-write pattern, but **do not replace the event loop's thread-ownership rule**.

### 4.2. Why Not Register `OP_WRITE` All the Time?

For a connected TCP socket, the send buffer can usually accept a small number of bytes even when you **have no data to send**. When `OP_WRITE` is always in the interest set, the selector can continuously report writable:

```text
select() -> OP_WRITE
application has no data to send -> return
select() -> OP_WRITE
application has no data to send -> return
... repeats continuously, CPU spikes
```

This is a **busy loop** caused by event loop design, not proof of heavy network traffic. Practical rule: only enable `OP_WRITE` when a queue/buffer has pending bytes, and once `write()` empties the buffer, **clear the write bit** immediately.

## 5. Ready Set: Readiness Is a Signal for an I/O Attempt

After calling one of the selection methods, the application can inspect:

```java
int ready = key.readyOps();
boolean readable = (ready & SelectionKey.OP_READ) != 0;
boolean writable = key.isWritable();
boolean acceptable = key.isAcceptable();
boolean connectable = key.isConnectable();
```

The four convenience methods check the corresponding readiness bit on a valid key. They **do not send/receive data** and do not prove that the next operation will complete the entire task.

### 5.1. The Ready Set Does Not Necessarily Match the Interest Set

You can have:

```text
interestOps = OP_READ | OP_WRITE     (application wants both)
readyOps    = OP_WRITE               (selector only saw writability)

or:
interestOps = OP_READ                (currently only asking to read)
readyOps    = OP_READ                (saw readable/EOF)

then the application changes interestOps = 0
readyOps may still retain OP_READ in the selected snapshot.
```

You should not expect `interestOps()==readyOps()`. Even after updating interest ops while the selector is selecting, the change might **not affect the ongoing selection cycle**, depending on timing. This is why when another thread adds outbound data, the event loop must have an appropriate **wakeup/work queue** mechanism, rather than assuming any interest mask change is observed immediately.

### 5.2. “Ready” Flags That Are Easily Misread

**`OP_ACCEPT`:** a new connection may be accepted, but when using a non-blocking `ServerSocketChannel`, `accept()` can still return `null` if no pending connection remains at the moment of the call. Handle `null` normally; high-load servers often accept in a loop until `null`.

**`OP_CONNECT`:** a non-blocking TCP connect may have completed or encountered an error. You must call `SocketChannel.finishConnect()` to complete the process/observe the error. `key.isConnectable()` does **not** by itself mean the connection succeeded.

**`OP_READ`:** there may be bytes to read, or end-of-stream/error. On TCP, `channel.read(buffer)` returns `>0` if bytes are read, `0` if no bytes can be read right now in non-blocking mode, or `-1` when the peer has closed its sending side after all prior data has been read. EOF is when lifecycle handling must happen—do not treat it as an empty payload and keep trying to read forever.

**`OP_WRITE`:** at least some data may be written if the system allows. `channel.write(buffer)` can still return `0`; it may also push only part of `ByteBuffer.remaining()`. Do not `clear()` or discard the buffer while pending bytes remain.

### 5.3. Selected-Key Set Differs from Ready Set

`selector.selectedKeys()` is a set of **keys**; `key.readyOps()` is the set of **readiness bits of a single key**. A key can be ready for **multiple operations at the same time**, rather than appearing as two entries in the selected set.

`select()` does not automatically clear the entire selected-key set after you process it. The common pattern:

```java
// Illustrative snippet; selector has been created and is used by the event loop.
selector.select();

java.util.Iterator<java.nio.channels.SelectionKey> it =
        selector.selectedKeys().iterator();

while (it.hasNext()) {
    java.nio.channels.SelectionKey key = it.next();
    it.remove(); // Remove from selected set, does not cancel channel registration.
    if (!key.isValid()) {
        continue;
    }
    // Check isAcceptable/isConnectable/isReadable/isWritable...
}
```

`it.remove()` only **removes the processed selected-key entry**; it does not mean `key.cancel()`. `cancel()` is the operation that unregisters the key, and the selector's complete removal of the key from its sets may occur during a subsequent selection/key-cleanup pass.

## 6. Java 17+: Proving That Changing the Interest Set Does Not Clear the Old Ready Set

The next example opens a listening TCP socket on loopback, registers `OP_ACCEPT`, creates a client to connect to it, and then calls `select` to observe readiness. Once the `OP_ACCEPT` ready bit is received, the program sets `interestOps(0)` and reads the ready set again.

**File `InterestReadySnapshotDemo.java`:**

```java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;

public class InterestReadySnapshotDemo {
    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open()) {
            server.configureBlocking(false);
            server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            SelectionKey key = server.register(selector, SelectionKey.OP_ACCEPT);
            System.out.println("Interest ACCEPT: "
                    + ((key.interestOps() & SelectionKey.OP_ACCEPT) != 0));

            client.connect(server.getLocalAddress());
            long deadline = System.nanoTime() + 3_000_000_000L;
            while (selector.selectedKeys().isEmpty() && System.nanoTime() < deadline) {
                selector.select(200);
            }
            if (selector.selectedKeys().isEmpty() || !key.isAcceptable()) {
                throw new IllegalStateException("No accept readiness");
            }
            System.out.println("Ready ACCEPT: "
                    + ((key.readyOps() & SelectionKey.OP_ACCEPT) != 0));

            key.interestOps(0);
            System.out.println("Interest is zero: " + (key.interestOps() == 0));
            System.out.println("Previous ready ACCEPT retained: "
                    + ((key.readyOps() & SelectionKey.OP_ACCEPT) != 0));

            selector.selectedKeys().remove(key);
            try (SocketChannel accepted = server.accept()) {
                System.out.println("Accepted channel: " + (accepted != null));
            }
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 InterestReadySnapshotDemo.java
java InterestReadySnapshotDemo
```

**Compiled/run stdout verified in an environment supporting TCP loopback:**

```text
Interest ACCEPT: true
Ready ACCEPT: true
Interest is zero: true
Previous ready ACCEPT retained: true
Accepted channel: true
```

What the example proves:

1. `key.interestOps()` initially contains `OP_ACCEPT`: that is the **interest requested by the application**.
2. The client opens a loopback TCP connection; the server channel becomes acceptable; `select` causes the key to appear in the selected set and `readyOps()` has the `OP_ACCEPT` bit.
3. `key.interestOps(0)` clears the **current interest bit**; it **does not immediately modify the observed ready bit**. Therefore, the ACCEPT bit in the snapshot remains true.
4. `selector.selectedKeys().remove(key)` removes the key from the **selected set**, without cancelling the server channel.
5. `server.accept()` retrieves a pending TCP connection. Because this is a local experiment with one client and an already-observed condition, the example expects non-null; if an unusual environment fails to report readiness in time, it throws an exception rather than printing a fake result.

Note: this is an experiment where the **ready set already existed before changing the interest**; you should not infer from the result that every subsequent `select()` must still report `OP_ACCEPT` when the interest set is `0`.

## 7. The Four Operations in the Lifecycle of a Non-Blocking TCP Server

A TCP server using a Selector typically transitions channels through these states:

```text
ServerSocketChannel
    bind + register(OP_ACCEPT)
             │
             ▼
      isAcceptable()
             │
          accept()
             │
             ▼
  Accepted SocketChannel ──► configureBlocking(false)
             │
             ▼
      register(OP_READ)
             │
          isReadable()
             │
        read(ByteBuffer)
             │
     complete request per framing?
            /  \
          no    yes
          │      │
      keep READ  response to send
                 │
                 ▼
            enable OP_WRITE
                 │
             isWritable()
                 │
          write(pendingBuffer)
                 │
            bytes left?
             /    \
           yes     no
           │        │
        keep WRITE  clear WRITE, keep READ or close
```

On the **non-blocking client** side, there is an extra step at the beginning:

```text
SocketChannel.configureBlocking(false)
              │
     boolean connected = connect(remote)
              │
         ┌────┴────┐
       true       false
         │          │
    connected    register(OP_CONNECT)
    immediately     │
         │       isConnectable()
         │          │
         │       finishConnect()
         │          │
         └────┬─────┘
              ▼
   register/interest OP_READ
      or OP_WRITE if a buffer is ready to send
```

### 7.1. `OP_ACCEPT`: Only for Listeners

A server program typically does:

```java
// Illustrative, assuming selector and localAddress have already been created.
ServerSocketChannel server = ServerSocketChannel.open();
server.configureBlocking(false);
server.bind(localAddress);
server.register(selector, SelectionKey.OP_ACCEPT);
```

This is a **non-standalone illustrative snippet** because `selector`/`localAddress` must be initialized and released properly.

When `key.isAcceptable()`, call `((ServerSocketChannel) key.channel()).accept()`. The returned channel represents **an accepted TCP connection**; switch it to non-blocking before registering. Do not read application bytes directly from `ServerSocketChannel`.

### 7.2. `OP_CONNECT`: Completing a Non-Blocking TCP Connect

Calling `SocketChannel.connect(remote)` on a channel in non-blocking mode can return:

- `true`: the TCP connection completed immediately; typically register `OP_READ` and/or `OP_WRITE` as needed.
- `false`: connection is in progress; register `OP_CONNECT` and wait for readiness. When the key is connectable, call `finishConnect()`; if complete, switch interest away from `OP_CONNECT` to the needed I/O operations. `finishConnect()` can also throw an `IOException` such as `ConnectException`.

Do not register `OP_CONNECT` on a `SocketChannel` accepted from a server to “activate” the connection; it is already connected. Also do not treat an `isConnectable()` key as a success without handling `finishConnect()`.

### 7.3. `OP_READ`: Reading Until No More Data Can Be Read or a Message Is Complete

When `isReadable()`, you can call:

```java
int n = socketChannel.read(buffer);
if (n > 0) {
    // Received n bytes; buffer position advanced accordingly.
} else if (n == 0) {
    // Non-blocking socket temporarily has no more bytes to give.
} else {
    // n == -1: remote output has ended (EOF).
}
```

This is an **illustrative snippet**, not a standalone program. One readable event **is not necessarily one message**. The application must use a delimiter, length prefix, or parser to determine a complete request. If a request arrives in two parts, keep the inbound buffer or parser state in the attachment.

If you read `0`, do **not** run an infinite `while(true){read()}` loop hoping for more data; return to the Selector. If you read `-1`, close/cancel the channel according to the protocol, or if the application supports half-close, handle the receive-side state appropriately.

### 7.4. `OP_WRITE`: Enable Only When There Is a Pending Buffer

`ByteBuffer` maintains `position` and `limit`. With a buffer containing outbound data:

```java
int n = socketChannel.write(pending);
if (pending.hasRemaining()) {
    key.interestOpsOr(SelectionKey.OP_WRITE);
} else {
    key.interestOpsAnd(~SelectionKey.OP_WRITE);
}
```

The snippet above assumes `socketChannel`, `pending`, and `key` belong to **the same connection** and are managed by the event loop. A single `write` may write partially or return 0. Do not reassign `pending = null` while `hasRemaining()` is still true, otherwise you lose the part of the message not yet transferred to the socket buffer.

When writing finishes, keep `OP_READ` if continuing to wait for requests. If the protocol specifies closing the connection after the response, you may close the channel **after transferring the entire outbound buffer to the socket**, but understand: a completed write does not prove the peer has read/processed the bytes. To guarantee the remote application processed them, an application-level ACK is required.

## 8. Java 17+: One Selector Coordinating ACCEPT, CONNECT, READ, and WRITE

The full example below runs **a single Java process** on loopback. It creates a listening `ServerSocketChannel` and a client `SocketChannel`, both coordinated through **one `Selector`**. The application protocol is minimal:

- The client sends the UTF-8 string `PING\n`.
- The server accumulates bytes until a newline, then replies `PONG\n`.
- The client receives until the newline, and then the program prints the contents.

**All four readiness flags** play a role. On some operating systems, the client's `connect()` can complete immediately (`true`); in that case there is no need to wait for an `OP_CONNECT` event. The program handles **both cases**, rather than forcing a CONNECT event that is not guaranteed to occur.

**File `SelectorLoopbackDemo.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class SelectorLoopbackDemo {
    private static final class State {
        final boolean client;
        final ByteArrayOutputStream received = new ByteArrayOutputStream();
        ByteBuffer pending;
        String line;

        State(boolean client) {
            this.client = client;
            if (client) pending = StandardCharsets.UTF_8.encode("PING\n");
        }
    }

    private static void onRead(SelectionKey key, State state)
            throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        ByteBuffer buffer = ByteBuffer.allocate(128);
        int count = channel.read(buffer);
        if (count < 0) throw new EOFException("EOF before complete line");
        if (count == 0) return;
        buffer.flip();
        while (buffer.hasRemaining()) {
            byte value = buffer.get();
            if (state.received.size() >= 128)
                throw new IOException("Line too long");
            state.received.write(value);
            if (value == '\n') {
                state.line = state.received.toString(StandardCharsets.UTF_8)
                        .stripTrailing();
                if (state.client) {
                    key.cancel();
                    channel.close();
                } else {
                    state.pending = StandardCharsets.UTF_8.encode("PONG\n");
                    key.interestOps(SelectionKey.OP_WRITE);
                }
                return;
            }
        }
    }

    private static void onWrite(SelectionKey key, State state)
            throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        channel.write(state.pending);
        if (!state.pending.hasRemaining()) {
            if (state.client) {
                key.interestOps(SelectionKey.OP_READ);
            } else {
                key.cancel();
                channel.close();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open()) {
            InetAddress local = InetAddress.getLoopbackAddress();
            server.configureBlocking(false);
            server.bind(new InetSocketAddress(local, 0));
            server.register(selector, SelectionKey.OP_ACCEPT);

            client.configureBlocking(false);
            boolean connected = client.connect(server.getLocalAddress());
            State clientState = new State(true);
            client.register(selector,
                    connected ? SelectionKey.OP_WRITE : SelectionKey.OP_CONNECT,
                    clientState);

            State serverState = null;
            SocketChannel accepted = null;
            try {
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                while (clientState.line == null && System.nanoTime() < deadline) {
                    selector.select(500);
                    Iterator<SelectionKey> it = selector.selectedKeys().iterator();
                    while (it.hasNext()) {
                        SelectionKey key = it.next();
                        it.remove();
                        if (!key.isValid()) continue;
                        if (key.isAcceptable()) {
                            accepted = ((ServerSocketChannel) key.channel()).accept();
                            if (accepted != null) {
                                accepted.configureBlocking(false);
                                serverState = new State(false);
                                accepted.register(selector, SelectionKey.OP_READ,
                                        serverState);
                            }
                            continue;
                        }
                        State state = (State) key.attachment();
                        if (key.isConnectable()) {
                            SocketChannel ch = (SocketChannel) key.channel();
                            if (ch.finishConnect()) key.interestOps(SelectionKey.OP_WRITE);
                        } else if (key.isReadable()) {
                            onRead(key, state);
                        } else if (key.isWritable()) {
                            onWrite(key, state);
                        }
                    }
                }
                if (clientState.line == null || serverState == null
                        || serverState.line == null)
                    throw new IllegalStateException("Exchange incomplete");
                System.out.println("Server received: " + serverState.line);
                System.out.println("Client received: " + clientState.line);
            } finally {
                if (accepted != null) accepted.close();
            }
        }
    }
}
```

**Compile and run with JDK 17+:**

```bash
javac --release 17 -encoding UTF-8 SelectorLoopbackDemo.java
java SelectorLoopbackDemo
```

**Compiled and executed stdout verified on TCP loopback:**

```text
Server received: PING
Client received: PONG
```

Stage-by-stage breakdown:

1. `Selector.open()` creates the selector. `server.configureBlocking(false)` allows registration; `server.bind(..., 0)` uses local loopback and an ephemeral port so you do not have to pick a fixed port.
2. `server.register(selector, OP_ACCEPT)` monitors the listener. When acceptable, `accept()` returns the server's client-side peer channel; the server peer is switched to non-blocking and then registered with `OP_READ`.
3. The client calls `connect()` in non-blocking mode. If it completes immediately, the client is registered with `OP_WRITE` to send PING; otherwise, it waits for `OP_CONNECT`, calls `finishConnect()`, and then switches to `OP_WRITE`.
4. In `onWrite`, `SocketChannel.write(ByteBuffer)` may write **only part of the buffer**. `state.pending.hasRemaining()` determines whether `OP_WRITE` needs to be kept. Once the client finishes writing, its interest is changed to `OP_READ` to wait for the response; **`OP_WRITE` is not kept needlessly**.
5. The server receives `PING\n`; even if a read returns one byte at a time, `State.received` accumulates per connection until the newline. The server switches its interest to `OP_WRITE` to send `PONG\n`.
6. The server closes the accepted socket **after flushing the entire pending buffer**. The client reads the response until the newline and then closes the connection. In this lesson, the server intentionally handles **one request and one response**; this is not a production event loop supporting multiple requests per connection.
7. Each key in the selected set is removed with `it.remove()` before processing. `key.isValid()` skips cancelled/closed keys.
8. The `128`-byte limit per line is an **intentional limit of the demo protocol** to avoid accumulating arbitrary data; the 5-second deadline prevents the demo from waiting forever.

**Why doesn't the output print every SELECT event?** The ordering of `ACCEPT` and `CONNECT` readiness, the number of `READ/WRITE` rounds, and the byte count per call vary by OS/timing. Printing a specific event sequence and claiming stdout is always identical would be wrong. The two final output lines are verified to be deterministic **when the exchange completes successfully**.

**Limitations of the example:** only one client, only one line-based request, fixed response, error handling via exceptions, no backpressure queue, no accept burst handling, and no TLS. Real-world systems need per-connection read buffers, response queues, partial writes, backpressure, per-connection timeouts, and thorough cleanup.

## 9. Managing `OP_WRITE`, Backpressure, and Buffers Properly

### 9.1. Read/Write Cycles Are Not “One Event = One Message”

Applications usually must store state on `SelectionKey.attachment()`, for example:

```text
ConnectionState
  inboundBuffer
  parserProgress
  outboundQueue<ByteBuffer>
  currentWriteBuffer
  lastActivityTimestamp
  closingAfterWrite
```

This is a **structural diagram**, not standalone Java code. One readiness event can serve multiple messages; conversely, one message can also require multiple readiness events. `OP_READ`/`OP_WRITE` signal that I/O can be attempted, while **the application's parser and queue** determine logical processing.

### 9.2. Non-Blocking Write Pattern

When a new response is ready:

1. Encode the response into a `ByteBuffer` with a delimiter/length prefix according to the protocol.
2. Add the buffer to the queue of **the right connection**.
3. Enable `OP_WRITE` if the queue is non-empty.
4. When writable, write sequentially from the head of the queue. If `write(buffer)` returns `0` or `buffer.hasRemaining()` is still true, keep that buffer and return to the Selector.
5. When a buffer completes, remove it from the queue; continue with the next buffer within per-connection fairness limits.
6. When the queue is empty, **turn off `OP_WRITE`** to avoid spinning.

Pseudocode:

```text
onResponseQueued(connection, buffer):
    queue.add(buffer)
    key.interestOpsOr(OP_WRITE)

onWritable(key):
    while queue not empty:
        current = queue.peek()
        channel.write(current)
        if current.hasRemaining():
            break
        queue.remove()

    if queue empty:
        key.interestOpsAnd(~OP_WRITE)
```

This pseudocode outlines the algorithm while **omitting exception handling, per-round byte limits, channel closing, and thread synchronization**. A production server must also prevent one connection from writing too much in a single turn and starving other connections (*fairness*).

### 9.3. Backpressure

If a client reads slowly, `write` may write few or 0 bytes. When that happens, the **outbound queue grows** if the application keeps generating responses without bound. Selector does not make queues safe automatically. Define:

- Maximum capacity per connection and across the server.
- A threshold to pause reading (`OP_READ`) when the outbound queue becomes too full, if the protocol allows it.
- Timeout, rejection, or disconnection mechanisms for peers that are too slow.
- A cap on total bytes written per turn so one connection does not monopolize the event-loop thread.

**Do not remove OP_READ blindly** if protocol/control signals must still be received or resources freed. Backpressure behavior must follow the application contract.

### 9.4. Writing from Another Thread and `selector.wakeup()`

In a server where worker threads generate responses, a controllable pattern is for the worker to **put a task into a concurrent queue**, call `selector.wakeup()`, and let **the single event-loop thread** modify attachments, queues, and interest sets:

```text
Worker thread:
    completedResponses.add(taskForConnection)
    selector.wakeup()

Selector thread:
    select()
    drain completedResponses
    enqueue outbound buffers
    enable OP_WRITE for relevant keys
    process selected keys
```

`Selector.wakeup()` causes a blocked selection operation to return early (or affects the next select according to the API contract); it **does not by itself make a channel readable/writable**. You must drain the actual work queue and process readiness normally. Do not use `wakeup()` to fabricate a fake `OP_READ` event.

## 10. Common Selector Pitfalls

### Pitfall 1: Misunderstanding Interest Set vs. Ready Set

`interestOps()` is the **bit mask specifying requested monitoring**. `readyOps()` is the **readiness the selector has observed**. Changing the interest mask does not mean the ready set changes immediately. Use `key.isReadable()` or bitwise `readyOps & OP_READ` after select processing, not `key.interestOps() & OP_READ` as proof that the socket has bytes.

### Pitfall 2: Registering Invalid Flags

`ServerSocketChannel` only supports `OP_ACCEPT`; `SocketChannel` supports `OP_CONNECT/READ/WRITE`; `DatagramChannel` supports `OP_READ/WRITE`. Check `channel.validOps()` if your code selects flags dynamically. An invalid interest mask causes `IllegalArgumentException`, not a network timeout.

### Pitfall 3: Forgetting to Switch the Channel to Non-Blocking

Before `channel.register(selector, ops)`, the channel must be in **non-blocking mode**. If it is still blocking, `register` can throw `IllegalBlockingModeException`. A channel already registered with a selector also cannot arbitrarily be switched back to blocking mode while the registration remains active. Design the I/O lifecycle clearly.

### Pitfall 4: `OP_CONNECT` Is Ready, but `finishConnect()` Is Not Called

Detecting `key.isConnectable()` is not enough. For a connecting TCP socket, call `finishConnect()` and handle `IOException`. Once the connection completes, remove `OP_CONNECT` and enable `OP_READ/OP_WRITE` as needed; otherwise, the application may keep invalid state or attempt to read/write before the connect finishes.

### Pitfall 5: Keeping `OP_WRITE` Enabled When Nothing Needs to Be Written

If there is no outbound data yet `OP_WRITE` remains registered, the selector can continuously see the socket as writable, causing **CPU spin**. Only enable write interest when the pending buffer/queue is non-empty, and disable it as soon as it is empty.

### Pitfall 6: Confusing `OP_READ` with “A Full Message Is Available”

TCP is a **byte stream**; a read can return 0, a partial message, multiple concatenated messages, or -1 at EOF. Never use the length of a single `read` as a message boundary. Design framing (newline, length prefix, or parser), enforce size limits, and handle read 0/EOF separately.

### Pitfall 7: Forgetting to Remove the Selected Key After Processing

`selector.selectedKeys()` is not automatically cleared by the system as a “fresh event list” after each round. Use `Iterator.remove()` to remove the processed key, then wait for new readiness selection. `selectedKeys().clear()` can also be used when appropriate, but avoid clearing keys before their required work has been processed.

### Pitfall 8: Forgetting to Handle Cancelled Keys

A key can become invalid when its channel closes, the selector closes, or `key.cancel()` is called. Check `key.isValid()` before accessing state and catch/handle `CancelledKeyException` at appropriate boundaries. Cancellation is processed according to the selector's lifecycle; do not assume every key set becomes empty immediately on the very same line of code.

### Pitfall 9: Mistaking `select()`'s Return Value for the Number of Keys Waiting to Be Processed

The return value of `selector.select()` describes the keys whose ready-operation sets were updated during that selection operation, **not a fixed size of `selectedKeys()` after every call**. When selected keys remain from a previous round, the return value and the selected set size can differ. Read `selectedKeys()` and remove keys properly.

### Pitfall 10: Interpreting `select(0)` as “Do Not Wait”

In `Selector.select(long timeout)`, **timeout 0** means wait **indefinitely** until selected readiness, wakeup, or another API-defined return condition occurs; it is not immediate polling. If you need **non-blocking** selection, use `selectNow()`. Set a positive timeout to have a checkpoint for deadlines or other application tasks.

### Pitfall 11: Ignoring Fairness and Business Timeouts

One connection can be continuously writable or readable; an event loop that processes a single key endlessly will starve other channels. Cap bytes/messages processed per turn; update last-activity/deadlines, offload heavy work to a worker pool, and avoid blocking DB/HTTP calls directly on the selector thread.

### Pitfall 12: Treating Socket Closure Like Closing a Processed “Event”

`it.remove()` only removes the key from the selected set. `key.cancel()` cancels registration. `channel.close()` closes the channel (and renders the key unusable). Do not substitute these three operations for one another. When closing a connection, release buffers, discard pending tasks, and handle awaiting callbacks according to policy.

## 11. Diagnostic Workflow When the Event Loop Stops Working

### 11.1. Log Enough Context Without Spamming Every Selection Cycle

Every significant event should log:

```text
timestamp | channelId | remoteAddress | interestOps | readyOps
          | event=ACCEPT/CONNECT/READ/WRITE/CLOSE/ERROR
          | bytesRead | bytesWritten | queueBytes | reason
```

Because `OP_WRITE` can occur very frequently, do not log every writable occurrence in detail in production; aggregate metrics or log conditionally to avoid slowing down the system. During debugging, allow detailed logging to be enabled for a controlled period.

### 11.2. Observation Matrix

| Symptom | Common Cause | Check Step |
|---|---|---|
| `register` throws `IllegalBlockingModeException` | Forgot `configureBlocking(false)` | Verify order: open → non-blocking → register |
| `register` throws `IllegalArgumentException` | Used an OP not in `validOps()` | Print `validOps`, channel type, and mask |
| Server does not accept despite client connecting | Listener not bound/registered properly or selected keys not processed | Check `OP_ACCEPT`, `isAcceptable`, `accept()==null`, bound port |
| Client stays in connecting state | Forgot `finishConnect()` or connect actually failed | Check `OP_CONNECT`, `finishConnect` result, and exceptions |
| CPU near 100%, low traffic | `OP_WRITE` kept on continuously, or `selectNow` polling without pause | Print interest mask, pending queue, and select count |
| `isReadable()==true` but `read()==-1` | Remote closed its sending side | Handle EOF, do not create fake empty messages |
| `isWritable()==true` but only partial write succeeds | Instantaneous buffer/system limit | Keep position and `OP_WRITE` for remaining bytes |
| Client sent data but handler does not run | Incomplete message/framing read, not parsed, or key not removed | Track bytes, parser state, selected set |
| Changed `interestOps` but selector thread does not respond promptly | Changed while `select` was blocked waiting | Use work queue + `selector.wakeup()` |
| Entire server slows down due to one client | Blocking handler or unfair processing loop | Measure event loop duration, offload heavy work |
| Unexpected `CancelledKeyException` | Accessing key after close/cancel or race condition | Manage lifecycle and ownership |
| Only one client works | Shared state/buffer across multiple channels | Each key needs its own attachment/queue |

### 11.3. Distinguishing Application Errors from Network Errors

`OP_CONNECT` can be ready even when `finishConnect()` reveals the connection failed; this is a TCP-layer signal, not a “broken Selector”. `OP_READ` can be ready when the remote closes output; check `read()==-1` before concluding the parser is broken. If data is readable yet the application fails to process it, check **framing, buffer position/limit, thread state, and exception paths** before blaming the firewall.

Selector does not solve all connection errors: DNS can be wrong, a TCP port can be blocked, the server can crash, or the application can fail to process a response. Clearly separate **readiness**, **I/O result**, and **business result**.

### 11.4. Quick Review Checklist

- [ ] Channel is non-blocking before registration.
- [ ] `validOps()` contains the requested interest bits.
- [ ] Server listener uses `OP_ACCEPT`; accepted channels use `OP_READ/WRITE`.
- [ ] Non-blocking client handles both `connect()==true` and `connect()==false` + `finishConnect()`.
- [ ] After `select`, iterate `selectedKeys()` via an iterator and remove each key.
- [ ] Check `key.isValid()` and clean up on close/cancel/error.
- [ ] `read` handles `>0`, `0`, `-1`, and framing.
- [ ] `write` preserves buffer position/remaining on partial writes.
- [ ] `OP_WRITE` is enabled only when pending data exists; disabled when queue is empty.
- [ ] Event loop has timeouts/deadlines and performs no heavy blocking work.
- [ ] If changing interest/queues cross-thread, synchronization + `selector.wakeup()` is used.
- [ ] Tests exist that send a split request / long response to catch framing and partial I/O bugs.

## 12. Self-Check

**Question 1.** `interestOps()==OP_READ`, `readyOps()==0`. Can we conclude “there is data to read”?

**Answer:** No. The application **wants** to monitor reading, but the selector has not recorded readiness in the inspected ready set.

**Question 2.** After `key.isAcceptable()`, you call `accept()` and get a `SocketChannel`. Is it correct to register `OP_ACCEPT` on the newly accepted channel?

**Answer:** No. `OP_ACCEPT` belongs to `ServerSocketChannel`, whereas an accepted `SocketChannel` supports `OP_READ/WRITE`; you need `configureBlocking(false)` and then register appropriately.

**Question 3.** `SocketChannel.connect(remote)` returns `false`. Should you switch immediately to `OP_READ` or register `OP_CONNECT`?

**Answer:** Register `OP_CONNECT` and wait for connectable; call `finishConnect()`, and only switch to read/write once the connect actually completes.

**Question 4.** Does `key.isWritable()==true` mean an entire 2 MB response will be written in one call?

**Answer:** No. Non-blocking `write` can write partially or 0; preserve `ByteBuffer.position` and keep `OP_WRITE` enabled until sending completes.

**Question 5.** Why does CPU spike when there are only 5 idle clients, yet `OP_WRITE` is enabled on every channel?

**Answer:** Sockets are usually writable even when there are no bytes to send. The selector continuously reports writable, creating a busy loop. Disable `OP_WRITE` when the outbound queue is empty.

**Question 6.** After `key.interestOps(0)`, `key.readyOps()` still has the `OP_ACCEPT` bit. Is this a Java bug?

**Answer:** No. A new interest set does not automatically clear a ready set that was already recorded previously.

**Question 7.** After processing a key, does `it.remove()` close the socket?

**Answer:** No. It only removes the key from the **selected-key set**; it does not cancel the registration or close the channel.

**Question 8.** Is `selector.select(0)` a way to poll immediately like `selectNow()`?

**Answer:** No. A timeout of 0 in `select(long)` is a request to wait indefinitely per the contract; use `selectNow()` for non-blocking selection.

**Question 9.** `key.isReadable()` is true, but `read(buffer)==-1`. What is this situation?

**Answer:** The TCP input has reached EOF (the remote closed its sending side after prior data). This is not an empty message; lifecycle/protocol handling is required.

**Question 10.** Why must `selectedKeys().size()` not be assumed equal to the return value of `select()`?

**Answer:** The selected-key set can retain keys from previous rounds; the return value of select describes the keys whose ready-operation sets were updated in that selection call, not the total number of keys remaining in the selected set.

**Question 11.** What is the value of `OP_READ | OP_WRITE`? If you want to check only whether read is enabled, which operation do you use?

**Answer:** `1 | 4 = 5`; use `(ops & SelectionKey.OP_READ) != 0`.

**Question 12.** A worker thread adds a response to the outbound queue while the selector thread is waiting. What coordination pattern is appropriate?

**Answer:** Use a concurrent work queue, `selector.wakeup()`, and then let the event-loop thread dequeue the task, add the buffer, and enable `OP_WRITE`. `wakeup` does not itself provide fake readiness.

## 13. Conclusion

- **Interest set (`interestOps`)** = which operations the application wants to monitor; **ready set (`readyOps`)** = which operations the selector has seen as ready for attempting I/O. They are not the same thing.
- **`OP_ACCEPT`** for TCP listeners; **`OP_CONNECT`** for connecting non-blocking TCP clients; **`OP_READ`** for channels ready to attempt reading; **`OP_WRITE`** for channels ready to attempt writing.
- `SelectionKey` uses **bit masks**; use `|` to combine, `&` to test, and `validOps` to know what a channel supports.
- An event loop is the cycle **select → get selected keys → remove each key → process I/O → update interest mask**.
- Readiness does not guarantee completion: `accept()` can return null; `finishConnect()` can fail; `read()` can return 0 or -1; `write()` can write partially.
- **Only monitor `OP_WRITE` when there are actually pending bytes**, otherwise the event loop easily wastes high CPU.
- For real applications, you must manage connection state, framing, read/write buffers, timeouts, backpressure, thread ownership, and cleanup; Selector only assists with detecting I/O readiness.

### Official References (Java 17)

- [`SelectionKey` — interest set, ready set, valid operations, OP flags](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [`Selector` — registered keys, selected keys, select(), selectNow(), wakeup()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [`SelectableChannel` — configureBlocking(), register(), validOps()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html)
- [`ServerSocketChannel` — non-blocking accept](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [`SocketChannel` — non-blocking connect/finishConnect/read/write](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [`DatagramChannel` — supported operations for UDP](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
