# SelectionKey, Interest Set, and Ready Set in Java NIO Selector

## 1. The Problem: One Thread Monitoring Many Channels

With Java NIO, `Selector` enables one thread to monitor many `SelectableChannel` instances instead of dedicating a thread blocked on each `SocketChannel.read()`. The application registers the operations it wants to watch, calls `select()` to wait for channels to become ready, and then processes the selected keys.

Three concepts that are easily confused:

- **`SelectionKey`:** an object representing **a registration** between a `SelectableChannel` and a `Selector`.
- **Interest set:** the operations the application wants the selector to monitor, represented as a bitmask retrieved from `key.interestOps()`.
- **Ready set:** the operations that a selection pass determined are ready for the key, represented by `key.readyOps()`.

These are not three names for the same state. Look at the control flow:

```text
SelectableChannel (set non-blocking)
          │
          │ register(selector, OP_READ | OP_WRITE)
          ▼
   SelectionKey
          │
          ├── interestOps() : what the application WANTS to monitor
          ├── readyOps()    : what the selector detected as READY
          ├── channel()     : the registered channel
          ├── selector()    : the selector holding the registration
          └── attachment()  : application context, if any
          │
          ▼
  selector.select()
          │
          ▼
  selector.selectedKeys()
          │
          ▼
  check key.isReadable(), isWritable(), ...
          │
          ▼
  handle non-blocking I/O; adjust interestOps; remove key from selectedKeys
```

**Lesson objective:** understand the relationships among keys, interest sets, ready sets, and the selected-key set; use `OP_READ`/`OP_WRITE`/`OP_CONNECT`/`OP_ACCEPT` bitmasks; update interest at the right time; process selected keys safely; avoid busy loops and confusing "ready" with "I/O guaranteed to complete."

## 2. `SelectionKey` Is the Result of Registration

Basic API:

```java
Selector selector = Selector.open();
SelectableChannel channel = /* appropriate channel */;
channel.configureBlocking(false);
SelectionKey key = channel.register(selector, SelectionKey.OP_READ);
```

The snippet above is **illustrative only**: `channel` must be a type of `SelectableChannel` supporting `OP_READ`, and the caller must close the channel/selector when finished. `register` returns the `SelectionKey` bound to that channel–selector pair.

Key properties/methods:

| Method | Meaning |
|---|---|
| `key.channel()` | Accesses the channel of this registration |
| `key.selector()` | Accesses the selector associated with this registration |
| `key.interestOps()` | Reads the current interest bitmask |
| `key.interestOps(mask)` | Replaces the interest set with a new bitmask |
| `key.readyOps()` | Reads the key's readiness bitmask |
| `key.isReadable()`, `isWritable()`, `isConnectable()`, `isAcceptable()` | Convenience helpers checking bits in the ready set |
| `key.isValid()` | Whether the key is still a valid registration |
| `key.cancel()` | Requests cancellation of registration; processed during the next selection |
| `key.attach(obj)` / `key.attachment()` | Attaches and retrieves business context without altering readiness |

A `SelectionKey` is a **registration**, not a single event. The same key can be selected by the selector many times over the lifetime of a connection. Only one key is created for a channel–selector pair at a time; re-registering a channel with **the same selector** while a valid registration exists updates the existing registration's interest/attachment rather than creating a second independent key.

### 2.1. Non-Blocking Must Be Configured Before Registering

`SelectableChannel.register` requires the channel to be in non-blocking mode. With `SocketChannel`, `ServerSocketChannel`, or `Pipe.SourceChannel`, call:

```java
channel.configureBlocking(false);
```

If you register a selectable channel that is still blocking, `register` can throw `IllegalBlockingModeException`. Attempting to switch a selectable channel with an active valid registration back to blocking via `configureBlocking(true)` is likewise disallowed by the contract.

**Distinction:** `FileChannel` is not a `SelectableChannel`; ordinary disk files are not registered directly with a `Selector` under this model. `Selector` is especially useful for sockets and corresponding selectable channels.

## 3. `OP_*` Bits and `validOps()`

Java uses bitmask constants on `SelectionKey`:

| Constant | int Value | Monitored Operation | Typical Channels |
|---|---:|---|---|
| `SelectionKey.OP_READ` | `1` | Data available to read, EOF, or read no longer blocks per channel semantics | `SocketChannel`, `Pipe.SourceChannel` |
| `SelectionKey.OP_WRITE` | `4` | At least some bytes can be written without blocking | `SocketChannel`, `Pipe.SinkChannel` |
| `SelectionKey.OP_CONNECT` | `8` | Non-blocking connection can be completed | `SocketChannel` |
| `SelectionKey.OP_ACCEPT` | `16` | Server can accept a new connection | `ServerSocketChannel` |

Different bits can be combined with bitwise OR:

```java
int readAndWrite =
        SelectionKey.OP_READ | SelectionKey.OP_WRITE;

boolean wantsRead =
        (readAndWrite & SelectionKey.OP_READ) != 0;

boolean wantsAccept =
        (readAndWrite & SelectionKey.OP_ACCEPT) != 0;
```

This is an illustrative snippet that can be placed inside a method. The results are `wantsRead == true`, `wantsAccept == false`.

**Not every channel supports every operation.** Check:

```java
int supportedMask = channel.validOps();
boolean canRead =
        (supportedMask & SelectionKey.OP_READ) != 0;
```

The illustrative snippet requires `channel` to be an already-declared `SelectableChannel`. For example:

- `ServerSocketChannel`: typically only supports `OP_ACCEPT`.
- `SocketChannel`: supports `OP_CONNECT`, `OP_READ`, `OP_WRITE`.
- `Pipe.SourceChannel`: supports `OP_READ`.
- `Pipe.SinkChannel`: supports `OP_WRITE`.

If `register(selector, ops)` or `key.interestOps(ops)` receives a bit not in `channel.validOps()`, the API throws `IllegalArgumentException`. In particular, do not register `OP_ACCEPT` on a `SocketChannel` to wait for the server to accept a connection: only `ServerSocketChannel` has the accept role.

### 3.1. The Interest Set Can Be 0

`key.interestOps(0)` is a valid operation: temporarily monitor no I/O events on the key. It **does not remove the registration** and does not close the channel.

Applications can use `interestOps(0)` to pause processing while coordinating state; when ready to monitor again, set the desired bits. If the goal is to stop monitoring permanently, cancel the key or close the channel/selector per your lifecycle policy.

## 4. Interest Set: What Does the Application Want the Selector to Monitor?

`interestOps()` is the **intent bitmask** decided by application code. For instance, a socket after connecting might want to read while having no data waiting to send:

```java
key.interestOps(SelectionKey.OP_READ);
```

When the output queue has unsent data, add `OP_WRITE`:

```java
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
```

Once all data has been sent, remove `OP_WRITE`:

```java
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

The lines above are **illustrative code** with a valid `SelectionKey key` and a channel supporting both `READ` and `WRITE`. Bit combination operators used:

- `|` (OR): adds a bit while preserving other bits.
- `& ~` (AND NOT): clears a bit while preserving other bits.
- `&` (AND): tests whether a bit is enabled.

Since Java 11, `SelectionKey` also provides `interestOpsOr(ops)` and `interestOpsAnd(ops)` to update interest using atomic OR/AND operations relative to other interestOps calls:

```java
key.interestOpsOr(SelectionKey.OP_WRITE);     // Add WRITE.
key.interestOpsAnd(~SelectionKey.OP_WRITE);   // Remove WRITE.
```

This is an illustrative snippet requiring a valid key and channel support for `OP_WRITE`. The atomic bit-update APIs are useful when multiple threads modify interest; however, they **do not automatically synchronize the output queue, protocol state, or channel lifecycle**. Updating the bitmask and pushing data to the queue still require a consistent thread-safe protocol.

### 4.1. Changing Interest Does Not Overwrite the Ready Set Immediately

`key.interestOps(newMask)` changes what the selector will care about **in selection passes**. It does not mean `key.readyOps()` is cleared or recomputed instantaneously. The interest set and ready set are bitmasks with different purposes.

By the selector contract, when a selection is already in progress, a concurrently invoked interest change may not take effect until the next selection pass. When a worker thread adds data to a queue and enables `OP_WRITE`, it typically also calls `selector.wakeup()` to ask the event loop waiting in `select()` to wake up and handle the change.

## 5. Ready Set: What State Has the Selector Observed?

After `selector.select()`, a key may have:

```java
int ready = key.readyOps();

boolean canRead  = (ready & SelectionKey.OP_READ) != 0;
boolean canWrite = (ready & SelectionKey.OP_WRITE) != 0;
```

This is an illustrative snippet: `readyOps()` requires a valid key and should be read during the selected-key handling cycle. Readiness is commonly checked via:

```java
if (key.isReadable()) {
    // Try non-blocking read().
}
if (key.isWritable()) {
    // Try non-blocking write().
}
```

Methods like `isReadable()`/`isWritable()` inspect the **ready set**, not the interest set. A key can still retain ready bits detected from a prior selection pass even though interest has changed, so avoid treating `isReadable()` on an arbitrary key as an instantaneous socket state probe.

### 5.1. Ready Does Not Mean "The Operation Will Transfer All Data"

With a non-blocking `SocketChannel`:

- `isReadable()==true` means the selector detected a readable condition. `read(buffer)` can still return `0` in certain cases or `-1` on EOF; a single read is not guaranteed to yield an entire message.
- `isWritable()==true` only suggests it may be possible to write **some number of bytes** without blocking. `write(buffer)` can perform a partial write, and later return `0`.
- `isAcceptable()==true` signals you should try `server.accept()`; the non-blocking operation still must handle a `null` return per contract.
- `isConnectable()==true` indicates you should call `socket.finishConnect()`; the connection can still fail with an I/O exception.

Readiness is the condition to **attempt I/O via the appropriate API**, not a promise that the entire business request is complete. A message can span multiple bytes or frames; state must be preserved when data is incomplete.

### 5.2. How Is the Ready Set Updated While a Key Remains Selected?

A selector maintains a **selected-key set**. When a key is newly selected because an interest op is ready, its ready set is updated with the detected operations. If the key **is already** in the selected-key set, newly ready operations can be **ORed** into the existing ready bits instead of automatically resetting to a "current snapshot" model.

Consequence: `readyOps()` is not always the result of an instantaneous kernel check at the exact moment you read it. Bits can linger from an earlier selection cycle if the program leaves the key in the selected set.

The standard way to write an event loop is **take each selected key, handle it, and remove it from `selectedKeys()` via `iterator.remove()`**. In the next selection pass, if readiness persists, the selector can place the key back into the set.

## 6. The Three Sets of a Selector: Registered, Selected, and Cancelled

Besides the two **bitsets inside each key**, `Selector` manages **key sets**:

| Set | Retrieved via / Mechanism | Meaning |
|---|---|---|
| Registered-key set | `selector.keys()` | Keys currently registered with the selector |
| Selected-key set | `selector.selectedKeys()` | Keys selected and awaiting application handling |
| Cancelled-key set | Maintained internally by selector | Keys requested for cancellation, to be processed during a selection operation |

**Do not confuse** `selectedKeys()` (a set of key objects) with `key.readyOps()` (a bitmask inside a single key). They have different data types and meanings.

A key can be:

1. Registered and valid, but **not yet** in the selected set.
2. In the selected set, with ready bits recorded.
3. Removed from the selected set by the application after handling, while **remaining registered** to watch for future readiness events.
4. Canceled via `cancel()`, becoming invalid and deregistered through the selection process; no longer usable as a valid key.

### 6.1. Why Must You Call `iterator.remove()`?

A sample loop:

```java
Iterator<SelectionKey> iterator =
        selector.selectedKeys().iterator();

while (iterator.hasNext()) {
    SelectionKey key = iterator.next();
    iterator.remove(); // Key claimed for processing.

    if (!key.isValid()) {
        continue;
    }

    if (key.isReadable()) {
        // Perform non-blocking read until no more bytes are available, or up to quota.
    }
}
```

The code above is an illustrative snippet inside the lifecycle of an already-created selector, with `import java.util.Iterator` and `java.nio.channels.SelectionKey`. Using the iterator to remove from the selected set is the official and standard approach; `selectedKeys().add(...)` is unsupported.

**Removing from the selected-key set is not `cancel()`.** `iterator.remove()` only indicates the program has handled one notification round. The channel and registration remain active; the selector will select the key again if new or ongoing operations match its interest.

If you forget to remove:

- The event loop can reprocess an old key repeatedly under stale ready state.
- The number of "currently selected" keys will not accurately reflect new events.
- Ready bits can accumulate/OR across multiple selection rounds while the key stays in the selected set.
- It easily leads to duplicate processing or confusing observed results.

## 7. Runnable Java 17+ Example: Observing Interest and Ready on a Pipe

To avoid depending on network ports or external servers, this example uses `Pipe`. `Pipe.SourceChannel` supports `OP_READ` and can register with a selector; `Pipe.SinkChannel` writes data to the other end.

**Source file:** `SelectionKeyDemo.java`

```java
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class SelectionKeyDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            SelectionKey key = source.register(
                    selector, SelectionKey.OP_READ, "inbox");

            System.out.println("interestRead: "
                    + ((key.interestOps() & SelectionKey.OP_READ) != 0));

            ByteBuffer outbound = ByteBuffer.wrap(
                    "NIO".getBytes(StandardCharsets.US_ASCII));

            while (outbound.hasRemaining()) {
                sink.write(outbound);
            }

            System.out.println("selectMatched: "
                    + (selector.select(1000) > 0));

            Iterator<SelectionKey> iterator =
                    selector.selectedKeys().iterator();

            while (iterator.hasNext()) {
                SelectionKey selected = iterator.next();
                iterator.remove();

                if (selected.isValid() && selected.isReadable()) {
                    ByteBuffer inbound = ByteBuffer.allocate(16);
                    int count = source.read(inbound);
                    inbound.flip();

                    System.out.println("readyRead: "
                            + selected.isReadable());
                    System.out.println("readCount: " + count);
                    System.out.println("payload: "
                            + StandardCharsets.US_ASCII.decode(inbound));

                    selected.interestOps(0);
                }
            }

            System.out.println("interestAfter: "
                    + key.interestOps());
            System.out.println("selectedEmpty: "
                    + selector.selectedKeys().isEmpty());
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac SelectionKeyDemo.java
java SelectionKeyDemo
```

**Expected stdout in a normal environment without interrupts or spurious wakeups before data is selected:**

```text
interestRead: true
selectMatched: true
readyRead: true
readCount: 3
payload: NIO
interestAfter: 0
selectedEmpty: true
```

**Detailed explanation:**

1. `Pipe.open()` creates the source and sink ends. `Pipe` **does not** implement `AutoCloseable` itself; the example closes `source`, `sink`, and `selector` individually with `try-with-resources`.
2. `source.configureBlocking(false)` is required for registration. `source.register(selector, OP_READ, "inbox")` returns a key with READ interest; `"inbox"` is the attachment.
3. `sink.write(...)` puts three bytes `NIO` into the pipe. Next, `select(1000)` waits up to about one second to detect the readable source. With an internal pipe and data already present, the key is expected to be selected.
4. `selectedKeys()` holds the newly selected key. `iterator.remove()` deletes it from the selected set **without canceling the registration**.
5. `selected.isReadable()` checks the `OP_READ` ready bit. `source.read(inbound)` retrieves the three bytes, and `flip()` prepares for US-ASCII decoding into `NIO`.
6. `selected.interestOps(0)` temporarily turns off monitoring on the key after handling. The key remains valid until canceled or closed.
7. `selectedKeys().isEmpty()` returns `true` because the application removed the selected keys.

The example closes all three resources properly within scope. It prints no object identities, file paths, or random port numbers. If the selector is interrupted or the environment behaves unusually, selection can return 0; that is why a production event loop must always handle `select()` returning **with no keys**.

### 7.1. Reading Data After `isReadable` Still Requires Checking `read`

In the small example, `source.read` is expected to return 3. In real programs, `read` can return 0 when no more bytes are currently available or -1 when input ends; when data exceeds buffer size, you must continue reading and retain incomplete message parts for later processing.

**Do not infer that a READ-ready key contains exactly one message.** TCP is a byte stream and may contain half a message, multiple messages, or data split across arbitrary reads. A parser must maintain state to determine boundaries according to the protocol.

## 8. Minimal Selector Event Loop for Server/Socket

Below is an **algorithmic skeleton**, not a standalone program: it relies on `selector`, `server`, handlers, and queues defined by the application. Its purpose is to locate where ready bits are read and where interest is updated.

```java
while (running) {
    selector.select(); // May return with no keys.

    Iterator<SelectionKey> it =
            selector.selectedKeys().iterator();

    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove();

        if (!key.isValid()) {
            continue;
        }

        try {
            if (key.isAcceptable()) {
                acceptConnections(key);
            }
            if (key.isValid() && key.isConnectable()) {
                finishConnection(key);
            }
            if (key.isValid() && key.isReadable()) {
                readAvailableBytes(key);
            }
            if (key.isValid() && key.isWritable()) {
                flushPendingWrites(key);
            }
        } catch (IOException ex) {
            key.cancel();
            key.channel().close();
        }
    }
}
```

**This is Java-syntax pseudocode and does not compile on its own**: `running` and the four handler functions belong to the application. It illustrates the standard sequence:

1. `select()` waits for operations from keys the selector monitors.
2. Iterate the selected set, retrieve each key, and remove it from the set.
3. Check validity to avoid processing canceled keys.
4. Handle operations reported ready; handling may change `interestOps`, cancel the key, or close the channel.
5. Watch for I/O errors and connection lifecycle; do not keep invalid keys around for the next round.

Checking multiple `if` statements rather than `else if` makes sense when one key can be ready for multiple operations simultaneously. However, handlers can mutate/cancel the key, so the example checks `isValid()` before each subsequent operation.

### 8.1. Server: `OP_ACCEPT` and Registering Newly Accepted Channels

A non-blocking `ServerSocketChannel` is registered for `OP_ACCEPT`:

```java
server.configureBlocking(false);
SelectionKey acceptKey =
        server.register(selector, SelectionKey.OP_ACCEPT);
```

This is a snippet with `server` of type `ServerSocketChannel` and an already-created `selector`; the server must bind to an address/port before accepting connections.

When `acceptKey.isAcceptable()`:

```java
SocketChannel client = server.accept();
if (client != null) {
    client.configureBlocking(false);
    client.register(selector, SelectionKey.OP_READ);
}
```

This is an illustrative snippet requiring `SocketChannel` import, `IOException` handling, and closing the client on completion. `accept()` can return `null` when no pending connection exists at the moment of the call in non-blocking mode. For servers with many simultaneous incoming connections, it is common to loop `accept()` until `null`, bounded per iteration if fairness is needed.

**Mistake to avoid:** registering `OP_ACCEPT` on a client `SocketChannel`. Clients use the appropriate ops such as `OP_CONNECT`, `OP_READ`, and `OP_WRITE`.

### 8.2. Client: `OP_CONNECT` Does Not Replace `finishConnect()`

With a non-blocking `SocketChannel`, `connect(remote)` may not finish immediately. If still pending, register `OP_CONNECT`, and then when `isConnectable()`:

```java
SocketChannel client = (SocketChannel) key.channel();

if (client.finishConnect()) {
    key.interestOps(SelectionKey.OP_READ);
}
```

The illustrative snippet assumes `key` belongs to a connecting socket, with `IOException` handling and `SocketChannel` imported. `finishConnect()` can throw an exception if the connection fails. After connecting succeeds, remove `OP_CONNECT` and switch to the operations you actually need to watch. If bytes are waiting to be written, add `OP_WRITE` appropriately.

## 9. Why Does `OP_WRITE` Easily Cause a Busy Loop?

On a non-blocking socket, the OS usually has available space in its send buffer. Consequently, **`OP_WRITE` can be ready most of the time**, even when the application has zero bytes to send.

A dangerous pattern:

```java
client.register(selector,
        SelectionKey.OP_READ | SelectionKey.OP_WRITE);

// No data to write, yet OP_WRITE stays enabled for the lifetime of the connection.
```

This snippet has a non-blocking client, a valid selector, and a socket supporting both READ/WRITE. The selector can keep waking up for writability; CPU climbs even though the application has no work.

**Proper management with a write queue:**

- When the output queue is **empty**, interest normally only needs `OP_READ` (or other required bits), **not keeping `OP_WRITE`**.
- When enqueuing a message to send, add `OP_WRITE` and wake up the selector if another thread may be waiting.
- When the key is writable, call `SocketChannel.write(ByteBuffer)` to send **as many bytes as possible**, updating buffer position.
- If bytes remain unsent due to a partial write or returning 0, keep `OP_WRITE` to be notified when the socket becomes writable again.
- When the queue drains, **remove `OP_WRITE`**. Do not write once and assume the entire message was transmitted.

Illustrative bit-update code:

```java
// When pending data exists and the channel supports OP_WRITE:
key.interestOpsOr(SelectionKey.OP_WRITE);

// When no pending data remains:
key.interestOpsAnd(~SelectionKey.OP_WRITE);
```

Do not call these two lines back-to-back as a single real handler step: they illustrate **two different queue state moments**. And do not let non-I/O threads write to the socket concurrently with the event loop without an explicit synchronization agreement.

### 9.1. `isWritable()` Does Not Mean Sending Is Complete

`key.isWritable()==true` indicates write readiness; `write(buffer)` can still perform a partial write. Check `buffer.hasRemaining()` to keep partially written buffers and continue on later readiness. For framed protocols, preserve buffer order in the queue and avoid reusing a `ByteBuffer` while unsent bytes remain.

## 10. Changing Interest from Another Thread and `wakeup()`

An event loop might be waiting inside `selector.select()`. Meanwhile, a business processing thread produces response data and wants to write on the socket:

```java
// Worker thread: queue must be thread-safe.
pendingWrites.add(outgoing);

key.interestOpsOr(SelectionKey.OP_WRITE);
selector.wakeup();
```

This is a non-standalone illustrative snippet: `pendingWrites` is a concurrency-safe queue, `outgoing` is a buffer containing bytes, and `key` is valid and supports WRITE. Calling `wakeup()` tells the selector to leave its wait in `select()` (or causes the next select to return early per contract), letting the event loop handle the updated queue/interest.

Notes:

- `wakeup()` **does not** set `OP_WRITE` or readiness bits itself. It only triggers the wakeup mechanism.
- `interestOps` changes made while `select()` is running may only take effect on the following selection pass, depending on timing/semantics.
- `select()` can return 0 after a wakeup; that is valid, and the event loop must still run the step that processes enqueued work.
- You need coordination between the queue and interest to avoid races: between when the event loop sees an empty queue and turns off WRITE, another thread might enqueue data. You can funnel all interest updates onto the event-loop thread via a task queue + `wakeup()` to minimize risk.
- `SelectionKey.interestOpsOr/And` update the bitmask without losing concurrent updates from the interest API, but they **do not synchronize business data** or I/O ordering.

### 10.1. Distinguishing `select()`, `select(timeout)`, and `selectNow()`

- `select()`: may wait until a key is ready, woken up, interrupted, or another return condition occurs.
- `select(long timeout)`: waits up to the requested duration; with timeout `0`, the contract is to wait indefinitely just like `select()`, **not immediate polling**.
- `selectNow()`: performs non-blocking selection and returns immediately.

The return value is the number of keys whose ready set was updated by the current selection operation; **do not blindly equate it with `selectedKeys().size()`** if the application leaves previously selected keys across iterations. A select call can also return 0 on wakeup, interrupt, or timeout expiration; code should never assume returning guarantees at least one key.

## 11. `cancel()`, Closing Channels, and Checking `isValid()`

`key.cancel()` marks the key **no longer valid** immediately upon requesting cancellation and adds it to the selector's canceled-key processing flow. Removing the registration from the selector's sets is processed during the next selection per contract, not a guarantee that all internal structures are cleaned up instantaneously.

```java
key.cancel();
System.out.println(key.isValid()); // false
```

This is an illustrative snippet while `key` is still a `SelectionKey` object. After cancel, calling APIs that require a valid key such as `interestOps()` or `readyOps()` can throw `CancelledKeyException`. `channel()` and `selector()` still let you access the registration context, though that does not mean the key is still active.

**Distinguish these operations:**

| Operation | Closes channel? | Cancels registration? | Key still in selected set? |
|---|---|---|---|
| `selectedKeys().remove(key)` | No | No | Removed from selected set |
| `key.interestOps(0)` | No | No | May remain if not removed |
| `key.cancel()` | Does not auto-close channel | Requests cancel, key invalid immediately | Cleaned up in next selection |
| `key.channel().close()` | Yes | Closing channel cancels associated keys | Cleaned up per selector |
| `selector.close()` | Closes selector, invalidates registrations | Yes | Sets cleaned per contract; channels themselves do not necessarily close |

A socket I/O error handler typically calls both `cancel()` and `channel.close()`. Calling only `cancel` does not release the socket; only removing from the selected set does not cancel the registration.

### 11.1. What Is an Attachment Used For?

`key.attach(obj)` stores an application context object on the key. For example:

```java
final class ConnectionState {
    ByteBuffer input = ByteBuffer.allocate(4096);
    // Can add output queue, parser state, session id...
}

ConnectionState state = new ConnectionState();
key.attach(state);
ConnectionState retrieved =
        (ConnectionState) key.attachment();
```

This is illustrative code placed in a scope with a valid `SelectionKey key` and `ByteBuffer` imported; synchronization must be designed if the attachment is accessed from multiple threads. Attachments do not generate I/O readiness and do not hold "newly arrived messages" auto-decoded by the selector; they are simply a convenient place to hang parsers/buffers/queues managed by your program.

When canceling/closing, release resources referenced by the attachment per application policy to avoid memory leaks from objects still referenced in data structures.

## 12. SELECTED State Is Not a High-Level Subscription

NIO Selector can be viewed as a tool reporting **the ability to perform I/O operations**. It does not automatically:

- Split packets by newline, length-prefix, JSON, or custom protocols.
- Guarantee fairness across connections; one busy connection can monopolize processing time.
- Guarantee a single `read()` produces one exact message.
- Schedule retries or business timeouts.
- Guarantee event processing order across multiple threads if you implement concurrent handlers yourself.
- Provide end-to-end backpressure between producers, output queues, and sockets.
- Guarantee thread-safety of keeping/mutating attachments.

Real-world designs must separate the **event loop (readiness) layer** from the **protocol/application state layer (messages, retries, timeouts, backpressure)**.

### 12.1. Edge-Triggered vs. Level-Triggered: Do Not Over-Infer from the Java API

Different OSes have different notification mechanisms. Java `Selector` abstracts away provider details. Do not rely on assumptions like "one ready event = one new byte/packet/message," or that each select always yields a single event whose bit clears like a message queue.

A resilient programming model is: when selected, **attempt non-blocking I/O**, update buffers/queues, and adjust interest for the next cycle. For reads, typically keep reading until no more bytes can be fetched in that pass (or stop at a quota to preserve fairness); for writes, track unsent data and disable `OP_WRITE` once the queue empties.

## 13. Examples of Handling Differences Between Interest and Ready

### Case A: Only Interested in Reading, Socket Is Writable

```java
key.interestOps(SelectionKey.OP_READ);
```

Even if the OS socket is writable at that moment, the selector does not need to include the WRITE ready bit in notifications because the program is not interested in WRITE. **OS-level I/O capability** is not identical to the **application interest mask**.

### Case B: Want Both Read and Write, Only Read Is Ready

```java
key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
```

If the selector only detects READ ready in that pass, `isReadable()` is true while `isWritable()` can be false. The interest set has two bits; the ready set may have only one. Do not use `interestOps()` to decide whether to call `read()/write()` without inspecting readiness and queue state.

### Case C: Finished Processing, Then Changing Interest

The application receives READ-ready, finishes reading, and pauses reading to apply backpressure:

```java
key.interestOpsAnd(~SelectionKey.OP_READ);
```

The interest set no longer contains READ. However, `key.readyOps()` may still hold READ from the previous selection; merely changing interest does not erase the ready bit instantaneously. The application must use its own coordination state and operate by selection cycles, never re-invoking read solely because an old bit remains on the key.

### Case D: Canceled Key

```java
key.cancel();
boolean stillValid = key.isValid(); // false
```

Do not call `key.isReadable()` assuming the state is valid; an invalid key can throw `CancelledKeyException` when inspecting ready state. Only handle a key after `isValid()`, and still be prepared to catch I/O errors because state can change concurrently.

### Case E: Forgetting to Remove Key from the Selected Set

A key can still remain in `selector.selectedKeys()` when the event loop calls `select()` next time. Ready bits may accumulate/change under selected-key rules rather than giving a clean snapshot. Use `Iterator.remove` after retrieving a key to process, and do not turn the selected set into an application task queue.

## 14. Common Mistakes

1. **Registering a channel without `configureBlocking(false)`.** Can throw `IllegalBlockingModeException`.
2. **Confusing `FileChannel` with `SelectableChannel`.** `FileChannel` does not register with a `Selector` the way `SocketChannel` does.
3. **Using `OP_ACCEPT` on a client `SocketChannel`.** Only `ServerSocketChannel` supports accept; check `validOps()`.
4. **Assuming `interestOps()` and `readyOps()` are equal.** Interest is the monitoring request; ready is the selection result.
5. **Using `interestOps` to tell whether a channel is ready.** You must check readiness via `readyOps`/`isReadable` after selection and try I/O.
6. **Treating `isWritable` as meaning the entire buffer can be sent immediately.** Non-blocking write may transfer partially or return 0.
7. **Treating `isReadable` as guaranteeing a complete message.** You need a parser, leftover byte retention, and EOF handling.
8. **Leaving `OP_WRITE` constantly enabled while the output queue is empty.** Easily causes a busy loop and high CPU usage.
9. **Forgetting `iterator.remove()` when iterating `selectedKeys`.** Old keys persist across selection rounds, causing duplicate handling.
10. **Thinking removing from `selectedKeys` cancels the key.** They affect two different sets and serve different purposes.
11. **Calling `selectedKeys().add(key)` to synthesize fake events.** The API does not allow arbitrary insertion; use a separate task queue and `wakeup()`.
12. **Confusing the selected-key set with the ready set.** The set contains `SelectionKey` objects; the ready set is a bitmask on each key.
13. **Believing `readyOps()` always reflects OS state at this exact nanosecond.** Ready bits can linger from an earlier selection if the key was not removed from the selected set.
14. **Updating interest from a worker thread and expecting a waiting `select()` to pick it up immediately.** Understand the timing and call `selector.wakeup()` per protocol.
15. **Viewing `wakeup()` as "enabling `OP_WRITE`."** It only wakes the selector; you must update interest and prepare the actual queue.
16. **Using `key.interestOps(key.interestOps() | bit)` concurrently across threads without considering races.** Consider `interestOpsOr/And` or funneling updates onto the event-loop thread.
17. **Continuing to inspect ready/interest after `cancel()`.** Can trigger `CancelledKeyException`.
18. **Only canceling the key without closing a broken socket.** The registration goes away, but the channel resource still needs cleanup.
19. **Reading `select(0)` as "poll immediately."** For Java `Selector`, timeout 0 means wait indefinitely; use `selectNow()` to poll.
20. **Assuming the return value of `select()` always equals `selectedKeys().size()`.** If keys remain from an earlier turn, the two numbers can differ.
21. **Doing a single `read`/`write` and discarding unfinished data.** `ByteBuffer` `position`/`remaining` must be preserved in state.
22. **Running a long blocking handler on the selector thread.** Every other connection can stall; offload long tasks out of the event loop.
23. **Assuming `attach()` manages cleanup, timeouts, or thread safety automatically.** Attachments only store application references.
24. **Not handling `accept()==null` or failed `finishConnect()`.** Readiness only directs you to try I/O; it does not exempt you from handling races and exceptions.
25. **Registering `OP_READ`/`WRITE` outside `channel.validOps()`.** Throws `IllegalArgumentException`; verify capabilities for the channel type.

## 15. Knowledge Self-Check

**Question 1.** Does `SelectionKey` represent a single read event or a channel–selector registration?  
**Answer:** A registration. The same key can be selected multiple times.

**Question 2.** Does `key.interestOps()==OP_READ` guarantee `key.isReadable()==true` immediately?  
**No.** Interest is only the operation you want to monitor; readiness must be detected by the selector during selection.

**Question 3.** What is the difference between `selector.selectedKeys()` and `key.readyOps()`?  
**Answer:** `selectedKeys` is the set of selected `SelectionKey` objects; `readyOps` is the bitmask of ready operations on *a single key*.

**Question 4.** How do you test whether the `OP_READ` bit is enabled in a mask?  
**Answer:** `(mask & SelectionKey.OP_READ) != 0`. Do not use `mask == OP_READ` if multiple bits may be set.

**Question 5.** Why shouldn't `OP_WRITE` stay enabled all the time?  
**Because** sockets are usually writable whenever send buffer space exists, causing the selector to wake up continuously even when the output queue is empty.

**Question 6.** Does `iterator.remove()` close the channel?  
**No.** It only removes the key from the selected-key set without canceling registration.

**Question 7.** What should you do after `key.cancel()`?  
**Answer:** Do not inspect interest/ready on the invalid key; close the channel when no longer needed and let the selector process deregistration.

**Question 8.** Is `selector.select(0)` the same as `selectNow()`?  
**No.** A timeout of 0 in `select(long)` waits indefinitely; `selectNow()` is the non-blocking call.

**Question 9.** If a socket has `isWritable()==true`, can `write(ByteBuffer)` return 0?  
**Yes.** Readiness does not guarantee writing all data; keep unsent bytes and wait for another turn.

**Question 10.** A worker thread wants to send data over a socket managed by the event loop. Is `wakeup()` needed?  
**Usually yes** if the selector may be waiting: enqueue data via a thread-safe protocol, enable WRITE interest or send an interest-update task to the loop, and then call `wakeup()`.

**Question 11.** If a `SocketChannel` has not finished connecting, does one `isConnectable()` guarantee it is connected?  
**No.** You must call `finishConnect()` and handle exceptions, and only then update interest.

**Question 12.** Does a pipe `SourceChannel` support `OP_ACCEPT`?  
**No.** A pipe's `SourceChannel` only supports read; consult `validOps()` instead of forcing unrelated bits.

## 16. Takeaways and Official Documentation

**Operating formula:** register `SelectionKey` with an appropriate **interest set** → call `select` → iterate the **selected-key set** → read the **ready set** → perform non-blocking I/O → update state and interest → `iterator.remove()` to get ready for the next selection pass.

Distinctions you must remember:

- `interestOps` is **monitoring intent**, not proof the channel is ready.
- `readyOps` is **state recorded by the selector**, not a substitute for checking actual `read`/`write` results.
- `selectedKeys()` is the **set of keys to process**, not a bitmask; a key can be registered without being selected.
- `cancel`, `remove from selectedKeys`, and `interestOps(0)` are **three distinct actions**.
- Turn off `OP_WRITE` when the output queue is empty, use `selector.wakeup()` to coordinate the event loop with other threads, and manage non-blocking protocols with dedicated buffers/attachments.

Java SE 21 documentation:

- `SelectionKey` — `interestOps`, `readyOps`, `OP_*` bits, `cancel`, `attach`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html
- `Selector` — key sets, `select`, `selectNow`, `wakeup`, readiness update rules: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html
- `SelectableChannel` — `validOps`, `configureBlocking`, `register`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectableChannel.html
- `SocketChannel` — `connect`, `finishConnect`, `read`, `write`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html
- `ServerSocketChannel` — `accept`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ServerSocketChannel.html
- `Pipe` — `SourceChannel` and `SinkChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Pipe.html
