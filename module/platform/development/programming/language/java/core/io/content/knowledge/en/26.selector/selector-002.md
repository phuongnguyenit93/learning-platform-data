# Registering Channels in Non-Blocking Mode with Java NIO `Selector`

## 1. Objectives and Scope

In Java NIO, `Selector` allows a single thread to monitor the **I/O readiness state** (*readiness*) of multiple eligible channels, instead of dedicating a blocking thread to each socket. To have a selector monitor a channel, we must open the appropriate **`SelectableChannel`**, place it in **non-blocking mode**, and then register it with the `Selector` along with the set of **interest operations**.

After this lesson, you will:

- Understand the mandatory preconditions for `register(selector, ops)` to succeed: the channel must be a `SelectableChannel`, be open, be in non-blocking mode, and `ops` must be valid for that channel.
- Use the proper sequence: `configureBlocking(false)`, `Selector.open()`, `register(...)`, `select()`, and iterating `selectedKeys()`.
- Distinguish `interestOps` (what you want to monitor) from `readyOps` (what the selector has determined is ready); understand `SelectionKey` and attachments.
- Handle `IllegalBlockingModeException`, `IllegalArgumentException`, `ClosedChannelException`, key cancellation, and resource closing.
- Avoid two common bugs in event loops: forgetting to remove processed keys from the selected-key set and registering `OP_WRITE` continuously when there is no data to send.
- Write runnable **Java 17+** examples using `Pipe.SourceChannel` and `Selector` before moving on to real sockets.

This lesson focuses on **non-blocking channel registration** and its direct consequences. Larger TCP protocol design, framing, backpressure, and distributed networking topics are mentioned only to the extent needed for safe usage.

## 2. Three Roles: Channel, Selector, and Selection Key

A **`SelectableChannel`** is a channel class that can be registered with a selector. Typical types:

| Channel | Typical Valid Interest Operations | Meaning |
| --- | --- | --- |
| `ServerSocketChannel` | `SelectionKey.OP_ACCEPT` | The server socket has a new connection waiting for `accept()` |
| `SocketChannel` | `OP_CONNECT`, `OP_READ`, `OP_WRITE` | Complete a connection, readable, or writable |
| `DatagramChannel` | `OP_READ`, `OP_WRITE` | UDP datagram can be read/written |
| `Pipe.SourceChannel` | `OP_READ` | The read end of a pipe has bytes ready |
| `Pipe.SinkChannel` | `OP_WRITE` | The write end of a pipe is writable |
| `FileChannel` | **No selector registration operations** | File I/O, not a `SelectableChannel` |

Operation bits are **constants on `SelectionKey`**, such as `SelectionKey.OP_READ`, not on `Selector`. Do not guess the operation set from whether a channel has `read(ByteBuffer)` or `write(ByteBuffer)`: use `channel.validOps()`.

**`Selector`** manages registered channels and selects channels that have appropriate readiness. A single selector can hold many registrations.

**`SelectionKey`** represents a registration between **one channel and one selector**. The key holds:

- `channel()`: the registered channel.
- `selector()`: the selector owning the key.
- `interestOps()`: bitmask of operations the application currently wants to observe.
- `readyOps()`: bitmask of operations reported ready by the selection operation.
- `attachment()`: optional application state object.
- `isValid()`, `cancel()`: registration lifecycle status.

A key belongs to a **(channel, selector) pair**. If a channel is already registered with that selector, calling `register` again typically **updates the interest ops and attachment of the existing key**, rather than creating a second key for the same pair.

```text
                  Selector
                     |
       +-------------+-------------+
       |                           |
 SelectionKey A                SelectionKey B
 interestOps=OP_READ           interestOps=OP_ACCEPT
       |                           |
 Pipe.SourceChannel           ServerSocketChannel
       |                           |
  configureBlocking(false)    configureBlocking(false)
```

The diagram illustrates the meaning of registration, not a claim that these two channels always belong in the same application.

## 3. Why Must You Call `configureBlocking(false)`?

A newly opened selectable channel defaults to **blocking mode**. For example, `ServerSocketChannel.accept()` can block waiting for a connection, and `SocketChannel.read()` can block waiting for data.

For `Selector`, a registered channel **must be in non-blocking mode**. Standard procedure:

```java
try (Selector selector = Selector.open();
     ServerSocketChannel server = ServerSocketChannel.open()) {

    server.configureBlocking(false);
    server.bind(new InetSocketAddress("127.0.0.1", 0));
    SelectionKey key = server.register(
            selector, SelectionKey.OP_ACCEPT);

    // Start select/accept loop...
}
```

The snippet above is an **illustrative snippet**; it requires importing `java.nio.channels.Selector`, `ServerSocketChannel`, `SelectionKey`, `java.net.InetSocketAddress`, and handling `IOException` in the enclosing method. `port=0` lets the OS pick an ephemeral port; the example does not print the port, so it does not depend on the assigned value.

Points to remember:

1. `configureBlocking(false)` configures the channel; it **does not** create a selector and does not register implicitly.
2. `register(selector, ops)` binds the channel to the selector with an initial interest set; this call itself **does not wait** for readiness.
3. `selector.select()` is what waits for and selects keys whose registered operations have become ready.
4. Non-blocking does not mean every I/O call transfers all bytes immediately. `read/write` can return 0; `accept()` can return `null` if no connection is ready at the moment of the call.

If still in blocking mode, calling `register` throws **`IllegalBlockingModeException`**. The fix is to configure `false` before registering, **not** to catch the exception and ignore registration.

Once a channel is registered with a selector, you must not arbitrarily call `configureBlocking(true)`: switching back to blocking mode while a valid registration exists throws `IllegalBlockingModeException`. Calling `cancel()` on a key marks it canceled immediately, but **deregistration is processed during the selector's next selection operation**. Therefore, you should not assume all registrations have been wiped immediately across all threads just because cancel was called; manage lifecycle state explicitly.

## 4. Choosing Valid `interestOps` with `validOps()`

The `ops` parameter of `register(selector, ops)` is a **bitmask**, combinable with the bitwise OR operator `|`:

```java
int interests = SelectionKey.OP_READ | SelectionKey.OP_WRITE;
```

This is only combination syntax, **not a good default choice** for every channel. Each channel type supports only a specific subset of bits. Checking:

```java
int requested = SelectionKey.OP_READ;
if ((requested & ~channel.validOps()) != 0) {
    throw new IllegalArgumentException("Operation not supported");
}
```

The snippet assumes `channel` is a `SelectableChannel`. The expression `requested & ~channel.validOps()` finds any bit requested that is not present in `validOps`. If non-zero, do not register.

A few examples:

- `Pipe.SourceChannel` supports `OP_READ`. Registering it with `OP_WRITE` throws `IllegalArgumentException`.
- `Pipe.SinkChannel` supports `OP_WRITE`; do not use it as a readable channel.
- `ServerSocketChannel` cares about `OP_ACCEPT`; registering `OP_READ` on a server listener is the wrong operation type.
- `SocketChannel` supports `OP_CONNECT` to monitor an incomplete connection attempt, then typically switches interest to `OP_READ` and conditionally to `OP_WRITE`.

A value of `ops=0` is **valid**: the channel remains registered while temporarily interested in no operations. When needed, the application can update `interestOps` again; this is a useful technique for controlling backpressure.

`validOps()` reflects the capability of the channel type. It does not indicate that every operation is currently reported ready at the moment of inspection.

## 5. How Does `register` Create/Update a `SelectionKey`?

Two commonly used overloads:

```java
SelectionKey key = channel.register(selector, ops);
SelectionKey keyWithAttachment = channel.register(
        selector, ops, attachment);
```

This is an illustrative snippet; `channel`, `selector`, `ops`, and `attachment` must be declared.

An **attachment** is an application object stored alongside the key. For example:

- Input/output buffers for a socket.
- Connection ID and protocol processing state.
- An object holding state while reading headers and waiting for a full payload.

`SelectionKey.attach(object)` can replace the current attachment. `attachment()` returns that object, or `null` if none is attached. When re-registering the same channel/selector, using the overload without an attachment does not necessarily overwrite the attachment; use the overload with an attachment to set a new attachment explicitly.

Distinguish between:

| Operation | Effect |
| --- | --- |
| `register(selector, OP_READ)` | New registration or updates interest ops of an existing registration |
| `key.interestOps(OP_READ)` | Replaces the key's entire interest operation set |
| `key.interestOps(key.interestOps() | OP_WRITE)` | Adds OP_WRITE to existing interest ops |
| `key.interestOps(key.interestOps() & ~OP_WRITE)` | Removes OP_WRITE from the interest set |
| `key.attach(state)` | Attaches custom application state |
| `key.cancel()` | Cancels the registration; the key becomes invalid |
| `channel.close()` | Closes the channel; associated registrations are canceled |

**Updating `interestOps`** does not mean the readiness condition just changed or is reflected immediately in an already in-progress `select` call. If another thread modifies the interest set while the selector thread is waiting, design proper selector wakeup (`selector.wakeup()`) and synchronize application state.

## 6. Runnable Java 17+ Example: Registering `Pipe.SourceChannel` and Handling `OP_READ`

`Pipe` helps you learn selector behavior without depending on TCP ports or firewalls. The sink end writes a few short bytes; the source end is registered in non-blocking mode. This is a standalone program.

Save with filename **`PipeRegistrationDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class PipeRegistrationDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);

            SelectionKey key = source.register(
                    selector, SelectionKey.OP_READ, "message-source");

            System.out.println("registered=" + key.isValid());
            System.out.println("attachment=" + key.attachment());
            System.out.println("interestedInRead="
                    + ((key.interestOps() & SelectionKey.OP_READ) != 0));

            byte[] payload = "HELLO".getBytes(StandardCharsets.US_ASCII);
            ByteBuffer toSend = ByteBuffer.wrap(payload);

            // Sink is blocking by default, payload is small; write all 5 bytes.
            while (toSend.hasRemaining()) {
                sink.write(toSend);
            }

            ByteArrayOutputStream received = new ByteArrayOutputStream();

            while (received.size() < payload.length) {
                int selected = selector.select(2000);
                if (selected == 0) {
                    throw new IOException("Timed out waiting for readable pipe");
                }

                Iterator<SelectionKey> iterator =
                        selector.selectedKeys().iterator();

                while (iterator.hasNext()) {
                    SelectionKey selectedKey = iterator.next();
                    iterator.remove(); // Do not reprocess the old key on the next turn.

                    if (!selectedKey.isValid() || !selectedKey.isReadable()) {
                        continue;
                    }

                    ByteBuffer input = ByteBuffer.allocate(16);
                    int count = source.read(input);

                    if (count == -1) {
                        throw new IOException("Pipe ended before complete data");
                    }
                    if (count > 0) {
                        input.flip();
                        byte[] bytes = new byte[input.remaining()];
                        input.get(bytes);
                        received.write(bytes, 0, bytes.length);
                    }
                }
            }

            System.out.println("receivedBytes=" + received.size());
            System.out.println("text="
                    + received.toString(StandardCharsets.US_ASCII));
        }
    }
}
```

Compile/run on JDK 17+:

```bash
javac PipeRegistrationDemo.java
java PipeRegistrationDemo
```

Stdout if pipe, selector, and I/O operations all succeed:

```text
registered=true
attachment=message-source
interestedInRead=true
receivedBytes=5
text=HELLO
```

**Detailed explanation:**

1. `Pipe.open()` creates two linked ends. `source` receives data written by `sink`.
2. `source.configureBlocking(false)` must run **before** `source.register(...)`.
3. `register(selector, OP_READ, "message-source")` creates the key and attaches an optional label.
4. `sink.write(toSend)` transfers all 5 bytes of `HELLO`. The read event on source becomes ready without needing a network socket.
5. `selector.select(2000)` waits up to 2 seconds; if the system does not report readiness in that window, the program throws an error instead of pretending to succeed.
6. `selectedKeys()` is the **selected-key set**, which must be iterated and cleared via `iterator.remove()` once processed. Removing from the selected set does not equate to canceling the registration.
7. `source.read(input)` returns the number of bytes actually read. Because the channel is non-blocking, a read can return `0`; the program only appends to the result when `count > 0`.
8. Once 5 bytes have accumulated, the program prints `HELLO` accurately. It does not assume a single `read()` always receives the entire payload.
9. `try-with-resources` closes the channels and selector. Once source/sink are closed, do not continue using them.

**Note:** Real-world socket problems cannot know in advance when a complete message has arrived based solely on a single `OP_READ` event. You typically need buffers, framing (length prefix or delimiter), and logic to retain partial bytes. The pipe example uses a known 5-byte payload to focus on registration mechanics.

## 7. Runnable Java 17+ Example: Registration Errors

A common mistake is trying to register a channel while it is still blocking; another is picking an operation outside `validOps()`.

Save file **`RegistrationErrorsDemo.java`**:

```java
import java.nio.channels.IllegalBlockingModeException;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;

public class RegistrationErrorsDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            try {
                // SourceChannel defaults to blocking mode.
                source.register(selector, SelectionKey.OP_READ);
            } catch (IllegalBlockingModeException expected) {
                System.out.println("blocking registration rejected");
            }

            source.configureBlocking(false);

            try {
                // Source is read-only, cannot register OP_WRITE.
                source.register(selector, SelectionKey.OP_WRITE);
            } catch (IllegalArgumentException expected) {
                System.out.println("invalid operation rejected");
            }

            SelectionKey key =
                    source.register(selector, SelectionKey.OP_READ);
            System.out.println("read registration valid=" + key.isValid());

            try {
                // While a valid registration exists: cannot re-enable blocking.
                source.configureBlocking(true);
            } catch (IllegalBlockingModeException expected) {
                System.out.println("switch to blocking rejected");
            }

            key.cancel();
            System.out.println("valid after cancel=" + key.isValid());
        }
    }
}
```

```bash
javac RegistrationErrorsDemo.java
java RegistrationErrorsDemo
```

Stdout on a successful run:

```text
blocking registration rejected
invalid operation rejected
read registration valid=true
switch to blocking rejected
valid after cancel=false
```

The exceptions are **intentionally triggered scenarios for learning the API**, not recommended control flow for main logic. In real production code, validate your design and configure the channel before registering, consult `validOps()`, and control the key lifecycle.

When `key.cancel()` is called, `key.isValid()` becomes `false` immediately. The selector processes deferred deregistration during its next selection operation. **Do not** infer that an invalid key means all channel resources are closed: to stop using a channel, close the owning resource explicitly.

## 8. `Selector.select()`, `selectNow()`, and `wakeup()`

Common selection methods:

| Method | Behavior |
| --- | --- |
| `selector.select()` | May block until a selection event, wakeup, interrupt, or other contract condition occurs |
| `selector.select(timeoutMillis)` | Waits up to the specified timeout; a `0` return can be due to timeout or other causes |
| `selector.selectNow()` | Performs a non-blocking selection operation |
| `selector.wakeup()` | Causes a waiting selection operation (or the next selection in applicable cases) to return |
| `selector.selectedKeys()` | Set of keys placed in the selected-key set |
| `selector.keys()` | Set of keys currently registered with the selector (distinct from the selected-key set) |

The return value of `select()` is **the number of keys updated/added to the selected set in that selection pass**, not the number of bytes ready and not necessarily the number of new connections. One `SelectionKey` can represent multiple ready operations; do not sum bit counts and treat them as connection counts.

Calling `select(0)` does not mean "poll immediately"; in the Java API, a timeout of 0 means wait indefinitely. If the goal is a non-blocking check, use `selectNow()`.

`wakeup()` is useful when another thread has queued new work and needs the selector loop to update `interestOps` or process a close request promptly. When using a selector across multiple threads, safe management of task lists, keys, and wakeups matters just as much as the API calls themselves.

An event loop must handle cases where zero keys are selected while other work still needs to run; do not blindly treat every `0` return as EOF.

## 9. `interestOps` vs. `readyOps`: What the Application Wants vs. What the Selector Sees

A key may be interested in `OP_READ`, yet at the time of inspection have no bytes ready to read:

```text
interestOps = OP_READ        // monitoring intent
readyOps    = 0              // not yet reported ready
```

When the selector updates the key, it may report `readyOps` containing `OP_READ`:

```text
interestOps = OP_READ
readyOps    = OP_READ
```

Then calling `key.isReadable()` is more convenient than checking bits manually:

```java
if (key.isValid() && key.isReadable()) {
    // Attempt reading from the non-blocking channel and check bytes actually read.
}
```

This is a snippet, requiring `key` to be a `SelectionKey` provided by the selector. `isReadable()` should only be queried while the key is valid; inspecting invalid key state can throw `CancelledKeyException`.

Do not use `isReadable()` as a substitute for checking the result of `read()`. Readiness is instantaneous, especially when multiple threads or access paths touch a channel; after the event, `read()` can still return 0, read fewer bytes, or return `-1` if the peer has closed and no data remains.

`interestOps` is the **bitmask of desired monitoring**, `readyOps` is the **bitmask of reported ready operations**; they are not equivalent and must never be interpreted as a buffer length.

## 10. Iterating Selected Keys Properly

Typical event-loop skeleton:

```java
while (running) {
    selector.select();

    Iterator<SelectionKey> iterator =
            selector.selectedKeys().iterator();

    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove();

        if (!key.isValid()) {
            continue;
        }

        if (key.isAcceptable()) {
            // Accept connection (ServerSocketChannel).
        }
        if (key.isConnectable()) {
            // Finish connect (SocketChannel.finishConnect()).
        }
        if (key.isReadable()) {
            // Read data from channel.
        }
        if (key.isWritable()) {
            // Write pending data from output queue.
        }
    }
}
```

This is an **illustrative skeleton**, not a standalone program: `running`, `selector`, the handlers, and imports must be supplied by the application. It is intentionally not a complete TCP server.

### Why Must You Call `iterator.remove()`?

`selectedKeys()` retains keys that have been selected. If you do not remove a key after handling it, the application may unintentionally reprocess stale state on subsequent turns. `iterator.remove()` only **removes the key from the selected-key set**; it does not cancel registration or close the channel.

Do not call `selector.selectedKeys().clear()` before handlers have processed the data, because that drops the current turn's event list. Nor should you call `key.cancel()` merely because an event was handled: canceling stops registration for future turns.

### Handlers Must Check I/O Results

For `SocketChannel.read(buffer)`:

- `n > 0`: received `n` bytes.
- `n == 0`: no bytes available to read in this non-blocking call.
- `n == -1`: reached the end of the channel's input stream (EOF); close/update the connection per protocol.

For `SocketChannel.write(buffer)`, the result is the number of bytes **actually written**, which can be 0 or less than `buffer.remaining()` prior to the call. Therefore, retain unwritten bytes in an output buffer/queue rather than assuming everything was sent.

## 11. Moving to TCP: `OP_ACCEPT`, `OP_CONNECT`, and `OP_WRITE`

### 11.1. Server Accepting Connections

Basic flow:

```java
ServerSocketChannel server = ServerSocketChannel.open();
server.configureBlocking(false);
server.bind(new InetSocketAddress("127.0.0.1", 8080));

SelectionKey serverKey =
        server.register(selector, SelectionKey.OP_ACCEPT);
```

This is a snippet requiring imports, an already-open `Selector`, `IOException` handling, and server closing management. Port 8080 is just for illustration; in practice it may be in use or lack bind permissions.

When `serverKey.isAcceptable()`:

```java
ServerSocketChannel listener =
        (ServerSocketChannel) serverKey.channel();
SocketChannel client = listener.accept();

if (client != null) {
    client.configureBlocking(false);
    client.register(selector, SelectionKey.OP_READ);
}
```

Also a snippet: a non-blocking server's `accept()` **can return `null`** if no connection is currently ready. Each accepted client is a **new** channel; you must configure non-blocking mode on that client itself before registering it with the selector.

In real applications, attach connection state, prepare buffers, cap client counts, configure timeouts, and ensure the client is closed if the handler fails. Do not leak channels due to an exception between `accept` and `register`.

### 11.2. Client Non-Blocking Connect

`SocketChannel.connect(remote)` can:

- Return `true` if the connection completes immediately.
- Return `false` if the connection is in progress; in that case, typically register `OP_CONNECT` to wait for notification.

```java
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);

boolean connected = client.connect(remote);
int ops = connected
        ? SelectionKey.OP_READ
        : SelectionKey.OP_CONNECT;

client.register(selector, ops);
```

The snippet assumes `remote` is a valid `SocketAddress` and `selector` is already open. When the key is connectable, the handler must call `client.finishConnect()`, check the result, and handle `IOException` such as `ConnectException` if the connection fails. Once connected, update interest ops for subsequent work such as `OP_READ`.

Do not treat the `OP_CONNECT` event as absolute proof of a successful connection and skip `finishConnect()`. Nor should you register `OP_READ` and expect to read data before finishing the connect.

### 11.3. Why Does `OP_WRITE` Need to Be Enabled Conditionally?

On ordinary TCP, a socket is usually **writable** most of the time. If you keep `OP_WRITE` registered continuously even when the output queue is empty, the selector loop can wake up repeatedly with no work to do, causing high CPU usage.

Processing pattern:

1. When the application has bytes queued to send, try writing to the channel.
2. If not all bytes were written, keep the remainder in a queue/buffer and **add `OP_WRITE` to interest ops**.
3. When the key becomes writable, continue writing; each time, check how many bytes were actually written.
4. Once the output queue is empty, **remove `OP_WRITE`** while typically keeping `OP_READ`.
5. Avoid busy-looping when a `write()` call returns `0`; wait for the next readiness event.

Key update example (snippet):

```java
// Bytes remaining to send:
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// Once all bytes are sent:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

Check `key.isValid()` when operating in an environment with cancellation. In multithreaded applications, use appropriate synchronization if other threads also modify `interestOps`.

## 12. Canceling Keys, Closing Channels, and Switching Blocking Mode

Three operations with distinct effects:

| Operation | What Happens |
| --- | --- |
| `key.cancel()` | Key becomes invalid immediately; requests deregistration, channel is not automatically closed |
| `channel.close()` | Closes the channel; all associated registrations are canceled |
| `selector.close()` | Closes the selector and cancels registrations; **does not automatically close registered channels** |

After cancel, the key is no longer valid for controlling interest ops. When re-establishing registration, account for cancellation/deregistration status instead of repeatedly calling `register` after cancel expecting a brand-new valid key instantly.

To switch a registered channel back to blocking mode, you must ensure it is **no longer registered with any selector**; canceling keys and completing deregistration may take a selection pass to take effect. This ties into thread synchronization: avoid changing mode while the selector thread may still be processing that key.

If you want to stop the loop, it is best to:

1. Set a stop state in the application visible across threads.
2. Call `selector.wakeup()` if the selector thread is blocked in `select()`.
3. Let the event loop itself handle cleanup at a safe point: cancel keys, close channels, then close the selector.
4. Use `try-with-resources` or explicit cleanup for newly opened resources.

Do not confuse **removing from the selected-key set** with **canceling a registration** or **closing a channel**.

## 13. Key Exceptions During Registration

| Scenario | Exception / Result |
| --- | --- |
| Channel is still in blocking mode when calling `register` | `IllegalBlockingModeException` |
| Requested operation outside `validOps()` | `IllegalArgumentException` |
| Channel already closed | `ClosedChannelException` |
| Selector already closed | `ClosedSelectorException` |
| Setting blocking mode `true` while channel has a valid registration | `IllegalBlockingModeException` |
| Reading `interestOps` / `readyOps` from a canceled key | May throw `CancelledKeyException` |
| `SelectionKey.cancel()` | Key invalid; deregistration handled subsequently |
| `selector.select(timeout)` returns 0 | No new keys in result, possibly timeout/wakeup; not channel EOF |
| `SocketChannel.read(buffer)` returns `-1` | EOF on channel byte stream, not canceled key |

Note: exceptions can arise mid-flow when resources are closed by another thread. Checking `isOpen()` right before an operation is only a point-in-time observation; it cannot completely eliminate race conditions. Always handle errors at the I/O boundary.

## 14. Common Mistakes and How to Fix Them

1. **Registering before switching to non-blocking:** call `configureBlocking(false)` before `register`.
2. **Using `FileChannel` with `Selector`:** `FileChannel` is not a `SelectableChannel`; use synchronous file APIs or `AsynchronousFileChannel` depending on your goal.
3. **Registering the wrong operation:** `Pipe.SourceChannel` does not support `OP_WRITE`, and a server listener does not support `OP_READ`; check `validOps()`.
4. **Calling `isReadable()` on a canceled key:** check `key.isValid()` and design a clean lifecycle.
5. **Forgetting `iterator.remove()`:** the selected-key set retains old keys; remove them from the set after retrieving and handling them.
6. **Canceling the key after every event:** that stops monitoring the channel; only cancel when you truly want to deregister.
7. **Closing the selector and thinking sockets/channels are also closed:** you must explicitly own and close the channels.
8. **Keeping `OP_WRITE` on forever:** when no data is waiting to be written, write readiness tends to fire continuously, driving CPU usage up.
9. **Assuming readable means a whole frame is ready:** `read()` can return 0, read a partial chunk, or hit EOF; you need a stateful parser.
10. **Not handling pending TCP connections:** use `OP_CONNECT` and `finishConnect()` before reading/writing in the connected state.
11. **Using `selector.select(0)` to poll:** review the timeout contract; when you need non-blocking checking, use `selectNow()`.
12. **Changing interest ops from a worker without wakeup:** the event loop may stay blocked waiting for an old event; use a task queue and call `wakeup()` at the right time.
13. **Mistaking an attachment for an auto-synchronized state copy:** an attachment is just an application object reference; across threads, ensure proper synchronization/visibility.
14. **Calling `configureBlocking(true)` right after `key.cancel()` and assuming deregistration is finished:** deregistration is processed by the selector across its lifecycle and must be coordinated safely.
15. **Assuming the return value of `select()` equals bytes read:** that is the number of selected/updated keys, whereas byte counts must come from the I/O calls.

## 15. Practice Exercises

### Exercise A — Register a Channel in the Right Order

Create a `Pipe`, call `source.register(selector, OP_READ)` while the channel is still blocking, and observe the exception. Then call `source.configureBlocking(false)`, register again, write 3 bytes to the sink, and use `selector.select(timeout)` to wait for the event. When reading, explain the difference between the number of selected keys and the number of bytes read.

### Exercise B — Explore `validOps`

Print `source.validOps()` and test the `OP_READ` / `OP_WRITE` bits with bitwise operators. Why does `source.register(selector, OP_WRITE)` fail even though the pipe also has a writable `SinkChannel`?

### Exercise C — Modify `interestOps`

Register `OP_READ`, call `key.interestOps(0)`, and inspect `key.interestOps()`; then re-register/update back to `OP_READ`. Does setting 0 close the channel or cancel the key? Why?

### Exercise D — Design Partial Socket Writes

A socket has a 64 KiB output queue, but the first `write(buffer)` call only writes 8 KiB. How should you retain the remaining 56 KiB? When do you enable `OP_WRITE`, when do you clear it, and why shouldn't you call write in a tight loop when the result is 0?

### Exercise E — Proper Cleanup

Starting from `PipeRegistrationDemo`, add a case that cancels the key before closing the pipe. Observe `isValid()`. Explain why `selector.selectedKeys().remove(key)` does not replace `cancel()`, and why closing the selector does not close the channels.

## 16. Self-Check Questions

1. Can you call `register` directly on a `FileChannel`? Why or why not?
2. What is the difference between `Selector` and `SelectionKey`?
3. Why must you call `configureBlocking(false)` before `register`?
4. What data type is `SelectionKey.OP_READ | SelectionKey.OP_WRITE`, and is it always valid for every selectable channel?
5. What does `channel.validOps()` check? Is it synonymous with `readyOps()`?
6. A channel is already registered with selector A; does calling register on the same selector A a second time necessarily create an additional key?
7. When does `isReadable()` return true? Does it guarantee `read()` will return a complete message frame?
8. In an event loop, why should you call `iterator.remove()` right after retrieving a selected key to handle?
9. How do `SelectionKey.cancel()` and `SelectableChannel.close()` differ?
10. Does `selector.close()` automatically close all registered sockets?
11. When a non-blocking client calls `connect(remote)` and gets false, which operation bit must be monitored and which method completes the connection?
12. Why can keeping `OP_WRITE` enabled even when there is no data to send cause high CPU usage?
13. If the selector thread is waiting and another thread just enqueued data, what role does `wakeup()` play?
14. Do `select(0)` and `selectNow()` mean the same thing?
15. Why is the return value of `select()` not the number of readable bytes?

## 17. Java 17 Documentation

- [`SelectableChannel` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html): `configureBlocking`, `register`, `validOps`.
- [`Selector` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select`, `selectedKeys`, `wakeup`, closing the selector.
- [`SelectionKey` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `interestOps`, `readyOps`, `OP_READ/WRITE/ACCEPT/CONNECT`, `cancel`, attachment.
- [`Pipe` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Pipe.html): `SourceChannel/SinkChannel` pair.
- [`SocketChannel` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking connect, `connect`, and `finishConnect`.

## 18. Key Takeaways

The standard registration workflow is **open `SelectableChannel` → `configureBlocking(false)` → open `Selector` → `channel.register(selector, validOps, attachment)` → `selector.select()` → process selected keys → manage interest ops and cleanup**.

`SelectionKey` holds the set of operations the application **wants to observe** and the set of operations the selector **reports ready**. A readiness event is only a signal to **attempt I/O**, not a promise that a single `read/write` transfers everything. Check actual return values, remove processed keys from the selected-key set, enable `OP_WRITE` only when data is queued, and distinguish `cancel`, `close channel`, and `close selector`. That is the necessary foundation before building a reliable non-blocking socket event loop.
