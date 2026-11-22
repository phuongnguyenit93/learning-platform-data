# Iterating `selectedKeys` and Removing Processed Keys in Java NIO Selector

## 1. Why Must You Handle and Remove Each SelectionKey?

In non-blocking network programming with Java NIO, applications typically use an **event loop** to manage many sockets through a `Selector`. On each call to `selector.select()`, the system determines which registered channels have I/O operations that are **ready**. Those registrations are represented by `SelectionKey`.

After a selection pass, the program retrieves the set:

```java
Set<SelectionKey> selected = selector.selectedKeys();
```

**This is not a self-consuming queue.** The `selectedKeys()` set retains selected keys until the application actively removes them from the set (or when a key is canceled, as part of the selector's deregistration process). If you iterate and process keys **without removing them**, they can stay in the selected set on subsequent passes. Typical consequences include duplicate processing of stale readiness state, repeated logs, accessing buffers in the wrong phase, and an uncontrollable event loop.

Standard pattern:

```java
Iterator<SelectionKey> iterator =
        selector.selectedKeys().iterator();

while (iterator.hasNext()) {
    SelectionKey key = iterator.next();
    iterator.remove(); // Remove from the selected-key set.

    if (!key.isValid()) {
        continue;
    }

    // Handle readiness events reported for this key.
}
```

Most importantly: **`iterator.remove()` only removes the key from the currently selected set**; it does not implicitly close the socket or cancel the `SelectionKey` registration. The key can appear again in later `select()` calls if the channel remains registered, is interested in the corresponding event, and becomes ready.

## 2. Three Sets and Three States to Distinguish

Inside a `Selector`, properly understanding these three concepts prevents loop bugs:

| Concept | API | Meaning |
| --- | --- | --- |
| **Registered-key set** | `selector.keys()` | Keys currently registered with the selector; not a set for the application to mutate directly |
| **Selected-key set** | `selector.selectedKeys()` | Keys that a selection pass determined are ready for matching interests |
| **Canceled-key set** | Internal to `Selector` | Keys that have been canceled and await selector deregistration cleanup |

Two very different operations:

- **`iterator.remove()`** on `selectedKeys().iterator()`: takes a key out of the **selected-key set** after claiming work from the selection round. The registration remains alive if the key has not been canceled.
- **`key.cancel()`**: marks the key as **no longer valid**, requesting deregistration from the selector. Its removal from the registered set is handled by the selector at the appropriate point, typically during a subsequent selection operation.

`key.cancel()` **does not close the channel**. To end a connection, the application usually must call `channel.close()` and clean up connection state. Closing a channel also cancels associated keys, though that still does not exempt you from loop cleanup and resource management rules.

### Scenario Example

A socket is registered for `OP_READ` and has bytes waiting to be read:

1. `selector.select()` detects the socket is readable.
2. The socket's key is placed in `selectedKeys()`.
3. The loop takes the key and calls `iterator.remove()`.
4. The program calls `channel.read(buffer)`.
5. If the connection remains open, the key stays among valid registrations; when a readable condition appears on a new selection pass, the key can be selected **once again**.

**Do not `cancel()` every key after every read**, because doing so drops the registration and forces you to rebuild monitoring if you want to continue receiving data.

## 3. Standard Flow: select → iterate → remove → dispatch

Typical control flow:

```text
                    +---------------------+
                    | selector.select()   |
                    +----------+----------+
                               |
                               v
                    +---------------------+
                    | selectedKeys()      |
                    +----------+----------+
                               |
                               v
                    +---------------------+
                    | iterator.hasNext()? |
                    +----------+----------+
                               |
                       yes     |     no
                        +------+------> Return to select()
                        |
                        v
               key = iterator.next()
                        |
                        v
                iterator.remove()
                        |
                        v
                 key.isValid()?
                  /           \
                no            yes
                |              |
           skip key      handle readyOps
                |              |
                +-------+------+
                        |
                        v
                     next key
```

Steps worth remembering:

1. `select()` can return 0 (for example, due to wakeup or timeout). Not every wakeup has I/O to process.
2. `selectedKeys()` holds a **set** of results; key order is not guaranteed.
3. `iterator.next()` simply fetches the current element in the set.
4. `iterator.remove()` removes **the exact element just returned by the iterator**, safely mutating the set while iterating via that iterator.
5. `key.isValid()` checks whether the key is still valid before accessing readiness or updating interest.
6. Handle the appropriate flags: `isAcceptable()`, `isConnectable()`, `isReadable()`, `isWritable()`.
7. Exit the iterator loop and return to `select()` while the application has not stopped.

In a real event loop, add exception handling, connection closing, per-turn work limits, partial write queues, timeouts, and a selector shutdown mechanism.

## 4. Why Use `Iterator.remove()` Instead of Arbitrary Removal?

The following code **should not be used**:

```java
for (SelectionKey key : selector.selectedKeys()) {
    selector.selectedKeys().remove(key); // Wrong inside a for-each loop.
    // Handle key...
}
```

A `for-each` loop actually iterates via an iterator. Modifying the set's structure through another path while an iterator is active can throw `ConcurrentModificationException` or exhibit implementation-dependent behavior. Use the iterator of **that same set** and call `iterator.remove()`.

The right way:

```java
Iterator<SelectionKey> it =
        selector.selectedKeys().iterator();

while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();

    if (!key.isValid()) {
        continue;
    }

    // Dispatch based on the key's ready state.
}
```

**`iterator.remove()` must follow a valid `next()` call** and must not be called twice consecutively for the same element. Calling `remove()` before `next()` or a second time without another `next()` throws `IllegalStateException` per the `Iterator` contract.

Placing `remove()` **immediately after `next()`** ensures the key is taken out of the selected set even if the handler below skips or throws an error. This is a clean event-lifecycle choice; it does not mean `remove()` itself has finished draining bytes from the socket.

### Can `selectedKeys().clear()` Be Used?

`selector.selectedKeys().clear()` removes **all** keys from the selected set. At the API level, this set permits remove/clear; however, clearing everything prematurely drops keys **not yet handled** in the current round. Therefore, `clear()` is only appropriate when the application **intentionally discards all selected events** or has already snapshotted/dispatched them safely so no work is lost.

Do not call `clear()` before iterating a round of readiness notifications while expecting to process every event just received. The per-key `iterator.remove()` pattern is clearer and easier to control.

## 5. `remove()`, `cancel()`, `close()`, and `interestOps(0)`

| Operation | Removes key from selected set? | Registration still valid? | Channel still open? |
| --- | --- | --- | --- |
| `iterator.remove()` | Yes, for the key just retrieved | **Usually still valid** if not canceled | Unchanged |
| `key.cancel()` | Not a "consume selected event" mechanism; selector handles cancellation | **No**, key becomes invalid | Does not auto-close |
| `key.channel().close()` | Triggers cancellation of associated registrations, cleaned per selector lifecycle | No longer valid | **No** |
| `key.interestOps(0)` | Does not auto-remove a key already in the selected set | Can still be valid | Unchanged |

**Two different scopes:**

- **Consumed readiness**: retrieved the key's notification to process in the current select turn; use `iterator.remove()`.
- **Lifecycle/cancellation**: no longer want the selector to monitor the channel; call `key.cancel()` and decide whether `channel.close()` is needed.

When the peer closes its send side and `read()` returns `-1`, servers typically cancel the key and close the socket (if the protocol does not keep half-open connections). When only a few bytes of a message are read, do **not** cancel the key; keep state to wait for the remaining bytes.

`interestOps(0)` can pause readiness monitoring without canceling the registration. However, if the key was already placed in the selected-key set, you still need to consume/remove the entry from the old selection pass; changing interest is not a selected-key set cleanup operation.

## 6. `interestOps` and `readyOps` Are Not the Same

`SelectionKey` has two important bitsets:

- **`interestOps()`**: the I/O types the application wants to watch, such as `OP_READ` or `OP_READ | OP_WRITE`.
- **`readyOps()`**: the I/O types that selection recorded as ready for the key.

Convenience methods `isReadable()`, `isWritable()`, `isAcceptable()`, and `isConnectable()` reflect the corresponding ready bits; they **do not inspect `interestOps`**.

| Bit | Typical Channel | How to Handle |
| --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` | Call `accept()` and check for possible `null` return |
| `SelectionKey.OP_CONNECT` | Connecting `SocketChannel` | Call `finishConnect()`, handle errors / pending connect |
| `SelectionKey.OP_READ` | Connected `SocketChannel` | Call `read()`, check `>0`, `0`, `-1` |
| `SelectionKey.OP_WRITE` | `SocketChannel` with pending outbound data | Try `write()` on pending data, adjust interest when drained |

**A key can have multiple ready bits simultaneously.** Therefore, use independent `if` checks when multiple operations on the same channel may need processing in a single pass, rather than assuming `else if` covers all cases:

```java
if (key.isConnectable()) {
    // finishConnect() if connection is pending.
}
if (key.isValid() && key.isReadable()) {
    // read, preserving parser state.
}
if (key.isValid() && key.isWritable()) {
    // write pending data.
}
```

This is an illustrative snippet; real applications must inspect connection state, pending buffers, and specific channel types. On a `ServerSocketChannel`, only `OP_ACCEPT` is valid; never call `isReadable()` expecting to accept connections.

**Subtle point:** By the `Selector` contract, a key already in the selected set may have its ready operations updated in subsequent selection passes rather than being automatically removed. Thus, **failing to remove the key** causes you to keep observing the old key and potentially mix readiness states across passes. `iterator.remove()` cleanly delineates each handling turn.

## 7. Java 17+ Example 1: Pipe, Selected Key, and Registered Key

To observe `selectedKeys()` directly without an external network, we use `java.nio.channels.Pipe`. `Pipe.SourceChannel` can register with a `Selector` for `OP_READ`. `Pipe.SinkChannel` writes data into the pipe, making the source readable.

This example writes two ASCII bytes `OK`, receives them via selector, removes the selected key, and then checks:

- whether the selected set is empty;
- whether the key is still registered with the selector.

**File `SelectedKeysPipeDemo.java`:**

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.TimeUnit;

public class SelectedKeysPipeDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            SelectionKey registered =
                    source.register(selector, SelectionKey.OP_READ);

            ByteBuffer outgoing = ByteBuffer.wrap(
                    "OK".getBytes(StandardCharsets.US_ASCII));
            while (outgoing.hasRemaining()) {
                sink.write(outgoing);
            }

            ByteBuffer received = ByteBuffer.allocate(2);
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(5);

            while (received.hasRemaining()) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) {
                    throw new IOException("Selection timeout");
                }

                long timeoutMs = Math.max(1L,
                        TimeUnit.NANOSECONDS.toMillis(remaining));
                selector.select(timeoutMs);

                Iterator<SelectionKey> iterator =
                        selector.selectedKeys().iterator();

                while (iterator.hasNext()) {
                    SelectionKey key = iterator.next();
                    iterator.remove();

                    if (!key.isValid()) {
                        continue;
                    }
                    if (key.isReadable()) {
                        int n = source.read(received);
                        if (n == -1) {
                            throw new EOFException("Pipe closed early");
                        }
                    }
                }
            }

            received.flip();
            String message = StandardCharsets.US_ASCII
                    .decode(received).toString();

            System.out.println("Nhan duoc: " + message);
            System.out.println("Selected set rong: "
                    + selector.selectedKeys().isEmpty());
            System.out.println("Key van dang ky: "
                    + selector.keys().contains(registered));
            System.out.println("Key con hop le: "
                    + registered.isValid());
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac SelectedKeysPipeDemo.java
java SelectedKeysPipeDemo
```

**Stdout when I/O and selection operations complete:**

```text
Nhan duoc: OK
Selected set rong: true
Key van dang ky: true
Key con hop le: true
```

### Result Explanation

1. `source.configureBlocking(false)` is required to register with the selector.
2. `sink` writes two bytes, making `source` ready to read.
3. `select(timeoutMs)` selects the source's key upon readiness.
4. `iterator.remove()` only removes the current element from the **selected-key set**, without canceling the key.
5. `source.read(received)` reads available bytes. The outer loop continues if fewer than two bytes have arrived; therefore stdout does not depend on whether data arrives in one or multiple selection passes.
6. `selector.selectedKeys().isEmpty() == true` after every key has been removed.
7. `selector.keys().contains(registered) == true` and `registered.isValid() == true` show the registration is still alive.

The stdout lines do not print the count of `select()` calls, since how many times the event loop wakes up can vary with OS scheduling. The program prints only the final state under successful conditions.

**Note:** once `source`/`sink`/`selector` exit `try-with-resources`, the resources are closed. The key being valid at print time **does not mean it remains valid after the channel or selector closes**.

## 8. Java 17+ Example 2: TCP Server Selecting `OP_ACCEPT` and `OP_READ`

The second example demonstrates a loop closer to a server application:

- Open a `ServerSocketChannel` on loopback with an OS-assigned port.
- Set the server to non-blocking mode and register `OP_ACCEPT`.
- Have a connecting client send four ASCII bytes `PING`.
- When the selector reports accept-ready, the server creates a non-blocking `SocketChannel` and registers `OP_READ`.
- The event loop reads until all four bytes are received, always calling `iterator.remove()` for each retrieved key.
- Once the message is complete, the server **cancels the key and closes the accepted client** because the session is done.

**File `SelectedKeysTcpDemo.java`:**

```java
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

public class SelectedKeysTcpDemo {
    public static void main(String[] args) throws IOException {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {

            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);

            try (SocketChannel sender = SocketChannel.open()) {
                sender.connect(server.getLocalAddress());
                ByteBuffer outgoing = ByteBuffer.wrap(
                        "PING".getBytes(StandardCharsets.US_ASCII));
                while (outgoing.hasRemaining()) {
                    sender.write(outgoing);
                }

                String result = null;
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (result == null) {
                    long nanos = deadline - System.nanoTime();
                    if (nanos <= 0) {
                        throw new IOException("TCP selection timeout");
                    }

                    long timeoutMs = Math.max(1L,
                            TimeUnit.NANOSECONDS.toMillis(nanos));
                    selector.select(timeoutMs);

                    Iterator<SelectionKey> iterator =
                            selector.selectedKeys().iterator();

                    while (iterator.hasNext()) {
                        SelectionKey key = iterator.next();
                        iterator.remove();

                        if (!key.isValid()) {
                            continue;
                        }

                        if (key.isAcceptable()) {
                            SocketChannel peer = server.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(
                                        selector,
                                        SelectionKey.OP_READ,
                                        ByteBuffer.allocate(4));
                            }
                        } else if (key.isReadable()) {
                            SocketChannel peer =
                                    (SocketChannel) key.channel();
                            ByteBuffer buffer =
                                    (ByteBuffer) key.attachment();

                            int n = peer.read(buffer);
                            if (n == -1 && buffer.hasRemaining()) {
                                throw new EOFException(
                                        "Client closed before PING");
                            }

                            if (!buffer.hasRemaining()) {
                                buffer.flip();
                                result = StandardCharsets.US_ASCII
                                        .decode(buffer).toString();

                                key.cancel();
                                peer.close();
                            }
                        }
                    }
                }

                System.out.println("Nhan duoc: " + result);
                System.out.println("Selected set rong: "
                        + selector.selectedKeys().isEmpty());
                System.out.println("Server con mo: " + server.isOpen());
            }
        }
    }
}
```

Run:

```bash
javac SelectedKeysTcpDemo.java
java SelectedKeysTcpDemo
```

**Stdout when loopback connection and I/O succeed:**

```text
Nhan duoc: PING
Selected set rong: true
Server con mo: true
```

### What Does This Demonstrate?

- Within the same selector lifecycle, the server's key can become ready for **accept**, while the peer's key can become ready for **read**.
- Each retrieved key is **immediately removed from the selected set**; this is independent of whether the key is canceled.
- The server's key stays alive to accept further connections; the peer's key, having completed one message, is `cancel()`ed and its socket closed.
- `ByteBuffer` is attached via `register(selector, OP_READ, attachment)` and filled incrementally until four bytes arrive. It does not assume a single `read()` returns all four bytes.

In this example, `else if` fits because `OP_ACCEPT` and `OP_READ` are registered on **two different channel types** and each key serves only one branch. For a `SocketChannel` with both `OP_READ` and `OP_WRITE`, independently check each ready bit to handle, along with re-checking `key.isValid()` if an earlier handler might close the socket.

**Example scope:** the server only receives a single fixed four-byte message from one loopback client. Real applications need framing for TCP streams, buffer limits, send queues, per-connection timeouts, error cleanup, and an event-loop shutdown mechanism.

## 9. Readiness Does Not Mean Data Processing Is Complete

Suppose `selector.select()` reports a `SocketChannel` is ready to read:

```java
int count = socket.read(inputBuffer);
```

Possible outcomes:

| Result | Interpretation | Handling |
| --- | --- | --- |
| `count > 0` | Received exactly `count` bytes | Update parser/buffer state; keep registration if more needed |
| `count == 0` | This read made no progress | Do not spin; return to selector or adjust interest |
| `count == -1` | EOF on receive side | Finish or handle half-close per protocol |
| Throws `IOException` | I/O error | Clean up key/channel/buffer per policy |

Even when a key is selected as readable, `read` does not guarantee filling the buffer or returning a full message. Ready is the state of *being able to attempt I/O*, not a complete copy of data waiting around to be consumed at will.

Therefore:

- **`iterator.remove()`** means "I have pulled this round's readiness notification out of the set"; it **does not mean** "I have finished receiving all socket data."
- **`key.cancel()`** means "I no longer need this registration"; do not use it as a substitute for handling incomplete data.
- **`inputBuffer.compact()`** retains bytes not yet processed by the parser to receive more; it is completely different from removing a key from the selected set.

Separating these three layers — *event*, *registration*, *byte content* — is an essential principle when writing event loops.

## 10. Should `remove()` Come Before or After Handling?

Two styles appear in codebases:

```java
SelectionKey key = iterator.next();
iterator.remove();
process(key);
```

and

```java
SelectionKey key = iterator.next();
process(key);
iterator.remove();
```

Both rely on the same iterator API as long as `process` does not mutate the set being iterated. However, **placing `remove()` immediately after `next()` is the more resilient choice** when a handler might throw an exception, close a channel, or need to `continue` to the next key.

If code places `remove` after the handler and the handler throws an exception before reaching that line, the key remains in the selected-key set. Depending on how the loop recovers, that key might be reprocessed unintentionally.

If a special requirement demands deferring removal, a careful `try/finally` structure can be used, but you must avoid calling `remove()` in an invalid state and understand behavior when the iterator is altered. For most single-threaded event loops, the simplest approach remains **get key, remove immediately, then dispatch**.

## 11. Handling Exceptions Per Key to Avoid Breaking the Whole Loop

In production applications, one broken client should not by default halt the selector from serving all remaining clients. One handling pattern:

```java
Iterator<SelectionKey> it =
        selector.selectedKeys().iterator();

while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();

    if (!key.isValid()) {
        continue;
    }

    try {
        handleReadyKey(key);
    } catch (IOException ex) {
        key.cancel();

        try {
            key.channel().close();
        } catch (IOException closeError) {
            ex.addSuppressed(closeError);
        }

        // Log/record metrics with context, continue to other keys
        // if application policy permits.
    }
}
```

This is an **illustrative code snippet**: `selector` and `handleReadyKey` are undeclared, so it is not a standalone compilable program. Consider unchecked exceptions such as `CancelledKeyException`, `IllegalArgumentException`, or programming bugs that could arise; you should not unconditionally swallow all `RuntimeException`s and carry on as if nothing happened.

Only call `key.cancel()` when you genuinely want to stop monitoring the registration; for a peer I/O error that leads to closing the socket, that is usually the right call. Any state attached to the key (attachment) must also be released or have its backlog handled when ending the connection.

**Minimum rule:** isolate per-connection errors from selector-level errors; after a severe selector error, have a strategy to recreate or stop the event loop.

## 12. `selectedKeys()` vs. `keys()`

Two sets often confused because both contain `SelectionKey`:

```java
Set<SelectionKey> allRegistered = selector.keys();
Set<SelectionKey> readySelected = selector.selectedKeys();
```

- `keys()`: the set of registrations belonging to the selector. The returned set does not permit the application to add/remove keys directly; attempting to modify it can throw `UnsupportedOperationException`.
- `selectedKeys()`: the set of selected keys and **permits remove/clear**; the application cannot arbitrarily add keys to it.

When you call `iterator.remove()` from `selectedKeys()`, `keys()` can still contain that key. That is precisely what `SelectedKeysPipeDemo` demonstrated.

Also distinguish between a **selected** key and a **valid** key: a key that has had `cancel()` called may still be awaiting selector deregistration cleanup. Hence `key.isValid()` must be checked before accessing ready operations, and you should never infer state solely from the element count of a set.

## 13. Do Not Use `cancel()` to "Clear Selected Events"

This is an easy design mistake to make:

```java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();

while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();
    key.cancel(); // Wrong if you still want to keep monitoring the channel.

    // Next selection no longer has this registration for further I/O.
}
```

`key.cancel()` is **not** a mandatory step after every `read` or `write`. It is used when stopping monitoring of a channel or re-registering under a different strategy.

For example, a TCP client sends a 100-byte message, yet on the first pass the server only receives 20 bytes:

- Take the key from the selected set and call `iterator.remove()`.
- Read 20 bytes, update remaining bytes needed.
- **Keep the key valid and interested in `OP_READ`** to receive the remaining 80 bytes upon readiness.
- Do not `cancel()` and close the socket just because the first `read` did not get all 100 bytes.

Only when ending the connection or hitting an unrecoverable error should you cancel the key, close the channel, and clean up attachments/buffers. Note that reading 20 bytes does not prove the message is complete: TCP does not preserve application record boundaries; the parser must manage framing.

## 14. `OP_WRITE`: Why Removing the Key Is Not Enough to Prevent CPU Spinning

A TCP socket is frequently writable because the kernel still has space in the send buffer. If a program registers `OP_WRITE` even when **there is no data to send**, the selector can repeatedly report the key writable across selection passes. Even if `iterator.remove()` is called properly, the loop can still wake up continuously due to readiness that **genuinely exists**.

The proper approach is managing interest:

1. Enable `OP_WRITE` only when outbound data is pending.
2. When partially written, preserve `ByteBuffer.position()` and keep `OP_WRITE`.
3. Once the queue is completely sent, **turn off `OP_WRITE`** in `interestOps`.
4. If new data is enqueued, turn `OP_WRITE` back on and wake the selector if needed.

Example disabling write interest (illustrative):

```java
int interests = key.interestOps();
key.interestOps(interests & ~SelectionKey.OP_WRITE);
```

Code must validate that the key is valid, check send state, and synchronize if multiple threads interact. Do not wipe out `OP_READ` if you still need to receive requests. Changing `interestOps` changes which events to monitor in the future; it **does not replace** calling `iterator.remove()` on the currently selected key.

## 15. `select()`, `selectNow()`, Timeout, and the Main Loop

Three common selection modes:

| API | Behavior |
| --- | --- |
| `selector.select()` | Can wait until a key is ready, wakeup, interrupt, or corresponding termination condition |
| `selector.select(timeoutMs)` with positive timeout | Waits up to a duration in ms if no readiness yet; returns updated key count per contract |
| `selector.selectNow()` | Performs non-blocking selection and returns immediately |

**Note:** `select(0)` does not mean "poll immediately" in Java `Selector`; a timeout of 0 means wait indefinitely. To avoid blocking, use `selectNow()`.

`select` returning a positive number does not mean you just process that many elements starting at index 0: `selectedKeys()` is a **Set**, not an ordered array. Always iterate the actual set.

An event-loop pattern:

```java
while (running) {
    selector.select();

    Iterator<SelectionKey> it =
            selector.selectedKeys().iterator();

    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove();

        if (!key.isValid()) {
            continue;
        }

        // Dispatch to the appropriate handler.
    }
}
```

This is illustrative because `running` and `selector` are undeclared. In real applications, handle shutdown, `wakeup()` when state changes from another thread, timeouts, deregistration, and resource closing.

### Why Not Rely on Selected-Key Order?

`Set<SelectionKey>` does not promise prioritizing accept before read, or socket A before socket B. Handlers must be designed order-independently, and some keys may be handled on the next turn if readiness arises after the current selection. If an application needs *fairness* across connections, enforce a per-turn byte or task limit rather than relying on the natural iteration order of `selectedKeys()`.

## 16. Configuring Channels and Registering Keys Properly

A channel must be in **non-blocking mode** before registering with a selector:

```java
ServerSocketChannel server = ServerSocketChannel.open();
server.configureBlocking(false);
server.register(selector, SelectionKey.OP_ACCEPT);
```

This is an incomplete snippet because the server must be opened/bound, the selector declared, and resources closed.

A `SocketChannel` accepted from the server must be configured for the event-loop model:

```java
SocketChannel accepted = server.accept();
if (accepted != null) {
    accepted.configureBlocking(false);
    accepted.register(
        selector, SelectionKey.OP_READ, ByteBuffer.allocate(1024));
}
```

A channel with a valid selector registration cannot be switched straight back to blocking mode: `configureBlocking(true)` can throw `IllegalBlockingModeException`. If switching modes is intended, cancel the registration and let the selector complete key removal properly rather than merely calling `iterator.remove()`.

**`iterator.remove()` does not affect blocking mode.** After removing a key from the selected set, the channel remains in non-blocking mode and the key can still remain registered.

## 17. Common Errors and How to Fix Them

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Iterating `selectedKeys()` without removing elements | Keys can stay in the selected set across future turns | Call `Iterator.remove()` for each retrieved key |
| Calling `selectedKeys().remove(key)` inside `for-each` | Modifying set structure outside the iterator can break iteration | Iterate with an `Iterator` and call `it.remove()` |
| Calling `key.cancel()` after every read event | Cancels a registration that is still needed | Only cancel when truly stopping monitoring |
| Confusing `iterator.remove()` with closing a socket | Registration and channel are not closed | Close the channel explicitly when the connection ends |
| Calling `selectedKeys().clear()` before handling | Discards already-selected events | Remove each key after `next()` |
| Not checking `key.isValid()` | Can hit `CancelledKeyException` when inspecting state | Check validity and handle errors in proper scope |
| Using only `else if` for all ready bits | Can miss another operation that is ready simultaneously | Check applicable bits, recheck state after handlers |
| Not turning off `OP_WRITE` when queue is empty | Selector repeatedly reports writable, high CPU | Enable OP_WRITE only while outbound data is pending |
| Looping continuously when `read()==0` | Busy-spins with no data | Yield back to the event loop and wait for readiness |
| Interpreting `read()==0` as EOF | Closes peer prematurely | `read()==-1` is EOF |
| Not removing key if handler throws | Selected set may retain stale entries hindering recovery | Remove right after `next()`; clean up in catch |
| Sharing iterator/selected set across threads without sync | Race conditions, duplicate event handling | Designate one thread owning the event loop or synchronize strictly |
| Thinking `selector.keys()` supports `remove` directly | Registered set cannot be mutated arbitrarily | Use `cancel` to deregister |
| Thinking `select(0)` equals `selectNow()` | `select(0)` can wait indefinitely | Use `selectNow()` when you want to poll |
| Not keeping `ByteBuffer` across multiple reads | TCP messages split apart, parser breaks | Per-connection attachment/state and clear framing |

## 18. Thread-Safety and Resource Notes

`Selector` supports selection and registration operations, yet **the selected-key set is not an automatically thread-safe multithreaded event queue**. If one thread iterates and removes while another thread modifies the selected set, you must enforce synchronization and ownership, or else encounter races and unpredictable state.

Common design: **one event-loop thread owns `selectedKeys()` and `select` calls**, while worker threads pass messages or tasks via a queue. When interest needs updating or the event loop needs to process new work, use a wakeup mechanism like `selector.wakeup()` paired with a properly synchronized queue. Never assume calling `wakeup()` alone suffices to synchronize data in application structures.

A key can carry an `attachment` (via `key.attach(value)` or `register(selector, ops, attachment)`) to hold parser state, inbound/outbound buffers, or connection metadata. When closing a connection, remember to release references to buffers/tasks to avoid retaining memory longer than necessary.

Handlers must also avoid blocking for long periods on the event-loop thread: heavy CPU work, blocking database queries, or prolonged blocking logging will stall all other keys. A `selectedKeys()` round succeeding at the API level does not guarantee responsiveness under load.

## 19. Knowledge Check Exercises

### Case A: Key Removed but Not Canceled

A valid `SelectionKey k` registered for `OP_READ` is selected by the selector. The handler executes:

```java
SelectionKey k = iterator.next();
iterator.remove();
```

Can `k` still be selected in a future `select()` pass?

**Yes.** `iterator.remove()` only removes it from the selected set without canceling the registration. When the channel continues having readiness matching its interest and the key remains valid, the selector can select the key again.

### Case B: Canceled Without Closing Channel

The handler calls:

```java
key.cancel();
```

Is the channel guaranteed to be closed?

**No.** `cancel()` cancels the registration; it does not close the channel automatically. To terminate the socket, an explicit resource-closing policy is needed. A canceled key is no longer valid, while its removal from the selector's registered set is processed according to the selection lifecycle.

### Case C: Key Both Readable and Writable

A `SocketChannel` key has `readyOps()` containing both `OP_READ` and `OP_WRITE`, and the application has outbound data pending. If the handler only has:

```java
if (key.isReadable()) {
    readFromPeer();
} else if (key.isWritable()) {
    writeToPeer();
}
```

What can happen?

**The write branch is skipped** in that round whenever read is true, even though write is also ready. This is an incomplete illustration since the two handler methods need declarations. If the design requires handling both, use two independent conditions and ensure the key remains valid after the first branch.

### Case D: Selected Set Empty While Registered Set Non-Empty

After handling:

```text
selector.selectedKeys().isEmpty() = true
selector.keys().isEmpty() = false
```

Is something wrong?

**No.** This is normal state: the selected events for this pass have been consumed, while the selector continues monitoring the remaining registered channels.

### Case E: Slow Sending

A writable key is handled and `socket.write(buffer)` returns 0. Should the handler immediately `cancel()` the key and close the socket?

**Not by default.** A 0 return from non-blocking write can simply mean no progress was possible at that instant. Keep the outbound buffer and `OP_WRITE` interest as appropriate, and return to the selector to wait until more bytes can be written. Only close on error, timeout, or business policy requirements.

## 20. Summary

**The selected-key iteration pattern to remember:**

```java
Iterator<SelectionKey> it =
        selector.selectedKeys().iterator();

while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove(); // Consume selected event, do not cancel registration.

    if (!key.isValid()) {
        continue;
    }

    // Dispatch appropriate event.
}
```

From this pattern, always remember four responsibility boundaries:

1. **`iterator.remove()`**: removes the key from the **selected-key set** for the current pass.
2. **`key.cancel()`**: requests canceling the **registration** when the application no longer wants to monitor the channel.
3. **`channel.close()`**: closes the **I/O resource** when the connection lifecycle ends.
4. **`interestOps(...)` and `ByteBuffer` state**: manage which readiness types to watch and remaining pending data.

Iterating keys properly does not replace handling partial reads/writes, EOF, framing, backpressure, or error handling. However, it is the foundation that keeps an event loop clear, prevents stale events from lingering unintentionally, and manages many connections in a controlled manner.

**Java SE 17 reference docs:** `java.nio.channels.Selector` (`selectedKeys()`, `keys()`, `select()`, `selectNow()`), `java.nio.channels.SelectionKey` (`cancel()`, `isValid()`, `interestOps()`, `readyOps()`), `ServerSocketChannel`, `SocketChannel`, `Pipe`, and `java.nio.ByteBuffer`.
